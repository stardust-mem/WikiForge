"""混合检索 — BM25 + 向量 + FTS5"""

import sqlite3

import jieba
from app.models.database import get_db
from app.search.embeddings import search_by_vector
from app.search.bm25_index import search_bm25


def _tokenize_zh(text: str) -> str:
    """jieba 分词，空格分隔（用于 FTS5 写入和查询）"""
    words = jieba.cut(text, cut_all=False)
    return " ".join(w.strip() for w in words if w.strip())


async def index_page_fts(page_id: str, title: str, content: str) -> None:
    """将页面写入 FTS5 全文索引（jieba 预分词）— 保留兼容"""
    tokenized_title = _tokenize_zh(title)
    tokenized_content = _tokenize_zh(content)

    db = await get_db()
    try:
        # 先删除旧记录
        await db.execute(
            "DELETE FROM wiki_fts WHERE page_id = ?", (page_id,)
        )
        await db.execute(
            "INSERT INTO wiki_fts (page_id, title, content) VALUES (?, ?, ?)",
            (page_id, tokenized_title, tokenized_content),
        )
        await db.commit()
    finally:
        await db.close()


async def search_fts(query: str, top_k: int = 10) -> list[tuple[str, float]]:
    """FTS5 全文检索，返回 [(page_id, rank), ...]"""
    tokenized_query = _tokenize_zh(query)

    # If query is empty after tokenization, return empty results
    if not tokenized_query.strip():
        return []

    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            """SELECT page_id, rank
               FROM wiki_fts
               WHERE wiki_fts MATCH ?
               ORDER BY rank
               LIMIT ?""",
            (tokenized_query, top_k),
        )
    except sqlite3.OperationalError:
        # FTS5 syntax characters (*, ", OR, AND, NOT) can cause errors
        return []
    finally:
        await db.close()

    # FTS5 rank 是负数，绝对值越小越相关
    return [(row[0], -row[1]) for row in rows]


async def hybrid_search(
    query: str,
    top_k: int = 7,
    bm25_weight: float = 0.4,
    vec_weight: float = 0.6,
) -> list[tuple[str, float]]:
    """
    混合检索：BM25 关键词 + 向量语义，加权合并排序。

    返回 [(page_id, combined_score), ...] 按分数降序。
    """
    # BM25 关键词检索（替代 FTS5）
    bm25_results = search_bm25(query, top_k=top_k * 2)
    # 向量语义检索
    vec_results = await search_by_vector(query, top_k=top_k * 2)

    # 归一化分数到 [0, 1]
    def _normalize(results: list[tuple[str, float]]) -> dict[str, float]:
        if not results:
            return {}
        scores = [s for _, s in results]
        min_s, max_s = min(scores), max(scores)
        span = max_s - min_s if max_s > min_s else 1.0
        return {pid: (s - min_s) / span for pid, s in results}

    bm25_scores = _normalize(bm25_results)
    vec_scores = _normalize(vec_results)

    # 合并
    all_pages = set(bm25_scores.keys()) | set(vec_scores.keys())
    combined = []
    for page_id in all_pages:
        score = (
            bm25_weight * bm25_scores.get(page_id, 0.0)
            + vec_weight * vec_scores.get(page_id, 0.0)
        )
        combined.append((page_id, score))

    combined.sort(key=lambda x: x[1], reverse=True)
    return combined[:top_k]
