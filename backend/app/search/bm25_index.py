"""BM25 搜索索引 — 基于 bm25s + jieba 分词"""

import logging
from pathlib import Path
from typing import Optional

import jieba
import numpy as np

from app.config import get_wiki_root, BASE_DIR

logger = logging.getLogger(__name__)

INDEX_DIR = BASE_DIR / "data" / "bm25_index"


def _get_all_wiki_pages() -> list[tuple[str, str]]:
    """扫描 wiki-root 下所有 .md 页面，返回 [(page_id, content), ...]"""
    wiki_root = get_wiki_root()
    pages = []
    for md_file in sorted(wiki_root.rglob("*.md")):
        rel = md_file.relative_to(wiki_root)
        parts = rel.parts
        # page_id = "category/slug" (strip .md suffix)
        if len(parts) >= 2:
            page_id = f"{parts[0]}/{rel.stem}"
        else:
            # top-level files like index.md, log.md — skip them
            continue
        content = md_file.read_text(encoding="utf-8")
        pages.append((page_id, content))
    return pages


def _tokenize(text: str) -> list[str]:
    """jieba 分词，返回 token 列表"""
    return [w.strip() for w in jieba.cut(text, cut_all=False) if w.strip()]


def build_bm25_index() -> int:
    """扫描所有 wiki 页面，构建 BM25 索引并保存到磁盘。返回索引文档数。"""
    import bm25s

    pages = _get_all_wiki_pages()
    if not pages:
        logger.warning("No wiki pages found, skipping BM25 index build")
        return 0

    page_ids = [pid for pid, _ in pages]
    corpus_tokens = [_tokenize(content) for _, content in pages]

    retriever = bm25s.BM25()
    retriever.index(corpus_tokens, show_progress=False)

    # Save index + corpus (page_ids as corpus for retrieval)
    INDEX_DIR.mkdir(parents=True, exist_ok=True)
    retriever.save(str(INDEX_DIR), corpus=page_ids)

    logger.info(f"BM25 index built: {len(pages)} pages -> {INDEX_DIR}")
    return len(pages)


def search_bm25(query: str, top_k: int = 10) -> list[tuple[str, float]]:
    """加载 BM25 索引，搜索并返回 [(page_id, score), ...]"""
    import bm25s

    if not INDEX_DIR.exists():
        logger.warning("BM25 index not found, returning empty results")
        return []

    query_tokens = _tokenize(query)
    if not query_tokens:
        return []

    retriever = bm25s.BM25.load(str(INDEX_DIR), load_corpus=True)
    n_docs = len(retriever.corpus) if retriever.corpus is not None else 0
    if n_docs == 0:
        return []
    results, scores = retriever.retrieve([query_tokens], corpus=retriever.corpus, k=min(top_k, n_docs), show_progress=False)

    # results[0] = array of corpus items for query 0, scores[0] = corresponding scores
    output = []
    for item, score in zip(results[0], scores[0]):
        if score > 0:
            # bm25s corpus items may be dicts or strings depending on save format
            if isinstance(item, dict):
                page_id = item.get("text", str(item))
            else:
                page_id = str(item)
            output.append((page_id, float(score)))

    return output
