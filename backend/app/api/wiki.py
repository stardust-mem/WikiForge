"""Wiki 浏览 API"""

from fastapi import APIRouter, HTTPException
from pathlib import Path

from app.config import get_wiki_root
from app.models.schemas import WikiPageDetail, WikiTree, WikiPageSummary

router = APIRouter()

CATEGORIES = ["entities", "concepts", "topics", "sources"]


def _extract_title(md_file: Path) -> str:
    """从文件的 frontmatter 中提取 title，fallback 到文件名 stem。"""
    try:
        for line in md_file.read_text(encoding="utf-8").split("\n"):
            if line.startswith("title:"):
                return line.split(":", 1)[1].strip().strip('"\'')
    except OSError:
        pass
    return md_file.stem


@router.get("/tree", response_model=list[WikiTree])
async def get_wiki_tree():
    """获取 Wiki 目录树"""
    wiki_root = get_wiki_root()
    trees = []
    for cat in CATEGORIES:
        cat_dir = wiki_root / cat
        pages = []
        if cat_dir.exists():
            for md_file in sorted(cat_dir.glob("*.md")):
                pages.append(WikiPageSummary(
                    page_id=f"{cat}/{md_file.stem}",
                    title=_extract_title(md_file),
                    category=cat,
                    source_count=0,
                ))
        trees.append(WikiTree(category=cat, pages=pages))
    return trees


@router.get("/page/{category}/{page_name}", response_model=WikiPageDetail)
async def get_wiki_page(category: str, page_name: str):
    """获取单个 Wiki 页面内容"""
    if category not in CATEGORIES:
        raise HTTPException(404, f"未知分类: {category}")

    wiki_root = get_wiki_root()
    file_path = wiki_root / category / f"{page_name}.md"
    if not file_path.exists():
        raise HTTPException(404, f"页面不存在: {category}/{page_name}")

    content = file_path.read_text(encoding="utf-8")
    title = _extract_title(file_path)

    return WikiPageDetail(
        page_id=f"{category}/{page_name}",
        title=title,
        category=category,
        content=content,
    )


@router.get("/index")
async def get_index():
    """获取 index.md 内容"""
    wiki_root = get_wiki_root()
    index_path = wiki_root / "index.md"
    if not index_path.exists():
        return {"content": "# 知识目录\n\n> 暂无内容"}
    return {"content": index_path.read_text(encoding="utf-8")}
