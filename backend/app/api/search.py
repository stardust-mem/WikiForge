"""搜索 & 问答 API"""

import json
import re

from fastapi import APIRouter, HTTPException

from app.models.database import get_db
from app.models.schemas import SearchRequest, SearchResult, QueryRequest, QueryResponse
from app.search.hybrid import hybrid_search, index_page_fts
from app.search.embeddings import store_embedding
from app.search.query import query_wiki as _query_wiki
from app.config import get_wiki_root

router = APIRouter()


@router.post("/search", response_model=list[SearchResult])
async def search_wiki(req: SearchRequest):
    """搜索 Wiki 页面"""
    results = await hybrid_search(req.query, top_k=req.top_k)

    wiki_root = get_wiki_root()
    output = []
    for page_id, score in results:
        parts = page_id.split("/", 1)
        if len(parts) != 2:
            continue
        category, name = parts
        file_path = wiki_root / category / f"{name}.md"
        snippet = ""
        title = name.replace("-", " ")
        if file_path.exists():
            content = file_path.read_text(encoding="utf-8")
            # 提取 title
            for line in content.split("\n"):
                if line.startswith("title:"):
                    title = line.split(":", 1)[1].strip().strip('"')
                    break
            # 去 frontmatter 取前 200 字符作为 snippet
            if content.startswith("---"):
                end = content.find("---", 3)
                if end > 0:
                    content = content[end + 3:].strip()
            snippet = content[:200]

        output.append(SearchResult(
            page_id=page_id,
            title=title,
            snippet=snippet,
            score=round(score, 4),
        ))
    return output


@router.post("/query", response_model=QueryResponse)
async def query_wiki(req: QueryRequest):
    """问答"""
    result = await _query_wiki(req.question)
    return QueryResponse(
        answer=result["answer"],
        citations=result["citations"],
        suggested_page=result.get("suggested_page"),
    )


@router.post("/archive")
async def archive_answer(req: dict):
    """将问答结果归档为新 Wiki 页面"""
    title = req.get("title", "").strip()
    category = req.get("category", "").strip()
    content = req.get("content", "").strip()
    source_question = req.get("source_question", "")

    if not title or not category or not content:
        raise HTTPException(400, "title, category, content 不能为空")
    if category not in ("entities", "concepts", "topics"):
        raise HTTPException(400, f"无效分类: {category}")

    wiki_root = get_wiki_root()

    # 生成 page_id（slug 化 title）
    page_name = title.lower().replace(" ", "-").replace("\u3000", "-")
    page_name = re.sub(r"[^\w\u4e00-\u9fff-]", "", page_name)
    if not page_name:
        raise HTTPException(400, "无法从 title 生成有效的页面名称")
    page_id = f"{category}/{page_name}"

    # 写入 wiki 文件
    cat_dir = wiki_root / category
    cat_dir.mkdir(parents=True, exist_ok=True)
    file_path = cat_dir / f"{page_name}.md"

    frontmatter = f'---\ntitle: "{title}"\ncategory: {category}\nsource: qa-archive\n---\n\n'
    file_path.write_text(frontmatter + content, encoding="utf-8")

    # 写入数据库
    db = await get_db()
    try:
        await db.execute(
            """INSERT OR REPLACE INTO wiki_pages
               (page_id, title, category, source_count)
               VALUES (?, ?, ?, 0)""",
            (page_id, title, category),
        )
        await db.execute(
            """INSERT INTO operation_log (op_type, target_id, detail)
               VALUES ('archive', ?, ?)""",
            (
                page_id,
                json.dumps(
                    {"title": title, "source_question": source_question},
                    ensure_ascii=False,
                ),
            ),
        )
        await db.commit()
    finally:
        await db.close()

    # FTS 索引
    await index_page_fts(page_id, title, content)
    # 向量嵌入
    await store_embedding(page_id, content[:2000])

    # 重建 BM25
    from app.search.bm25_index import build_bm25_index

    build_bm25_index()

    # 重建 index.md
    from app.wiki.index import rebuild_index

    rebuild_index()

    # Git 提交
    from app.wiki.git_ops import auto_commit

    auto_commit(f"archive: {title}")

    return {"page_id": page_id, "title": title, "category": category}
