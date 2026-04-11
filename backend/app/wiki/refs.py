"""页面间交叉引用 — 提取 [[wikilink]] 并写入 page_refs 表"""

import re
from pathlib import Path

from app.config import get_wiki_root
from app.models.database import get_db

CATEGORIES = ["entities", "concepts", "topics", "sources"]
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")


def _normalize(name: str) -> str:
    """统一名称：小写、空格/横线统一为横线"""
    return name.lower().replace(" ", "-").replace("_", "-").strip("-")


def _resolve_target(target: str, wiki_root: Path) -> str | None:
    """
    将 wikilink target 解析为 page_id。
    优先精确匹配 category/name，否则按分类搜索文件名。
    """
    target = target.strip()

    # 如果 target 本身是 category/name 格式
    if "/" in target:
        parts = target.split("/", 1)
        cat, name = parts[0], parts[1]
        norm = _normalize(name)
        file_path = wiki_root / cat / f"{norm}.md"
        if file_path.exists():
            return f"{cat}/{norm}"

    # 在所有分类目录中搜索
    norm_target = _normalize(target)
    for cat in CATEGORIES:
        cat_dir = wiki_root / cat
        if not cat_dir.exists():
            continue
        for md_file in cat_dir.glob("*.md"):
            if _normalize(md_file.stem) == norm_target:
                return f"{cat}/{md_file.stem}"

    return None


def extract_refs(
    page_id: str, content: str, wiki_root: Path
) -> list[tuple[str, str, str]]:
    """
    从页面内容中提取 [[wikilink]]，返回 [(from_page_id, to_page_id, context)]。
    跳过自引用和无法解析的 target。
    """
    refs: list[tuple[str, str, str]] = []
    seen_targets: set[str] = set()

    for line in content.split("\n"):
        for match in _WIKILINK_RE.finditer(line):
            inner = match.group(1)
            # 支持 [[target|label]] 格式
            pipe_idx = inner.find("|")
            target = inner[:pipe_idx] if pipe_idx >= 0 else inner

            resolved = _resolve_target(target, wiki_root)
            if not resolved or resolved == page_id:
                continue
            if resolved in seen_targets:
                continue
            seen_targets.add(resolved)
            # context 取当前行文本（去首尾空白，截断过长）
            ctx = line.strip()[:200]
            refs.append((page_id, resolved, ctx))

    return refs


async def rebuild_refs_for_pages(page_ids: list[str]) -> None:
    """增量更新指定页面的引用"""
    wiki_root = get_wiki_root()
    db = await get_db()
    try:
        # 1. 删除这些页面作为 from_page_id 的旧引用
        for pid in page_ids:
            await db.execute(
                "DELETE FROM page_refs WHERE from_page_id = ?", (pid,)
            )

        # 2. 重新提取并写入
        for pid in page_ids:
            parts = pid.split("/", 1)
            if len(parts) != 2:
                continue
            cat, name = parts
            file_path = wiki_root / cat / f"{name}.md"
            if not file_path.exists():
                continue
            content = file_path.read_text(encoding="utf-8")
            refs = extract_refs(pid, content, wiki_root)
            for from_id, to_id, ctx in refs:
                await db.execute(
                    """INSERT OR IGNORE INTO page_refs
                       (from_page_id, to_page_id, context)
                       VALUES (?, ?, ?)""",
                    (from_id, to_id, ctx),
                )

        await db.commit()
    finally:
        await db.close()


async def rebuild_all_refs() -> None:
    """全量重建：清空 page_refs 表，扫描所有页面重新写入"""
    wiki_root = get_wiki_root()
    all_page_ids: list[str] = []

    for cat in CATEGORIES:
        cat_dir = wiki_root / cat
        if not cat_dir.exists():
            continue
        for md_file in cat_dir.glob("*.md"):
            all_page_ids.append(f"{cat}/{md_file.stem}")

    db = await get_db()
    try:
        await db.execute("DELETE FROM page_refs")
        await db.commit()
    finally:
        await db.close()

    if all_page_ids:
        await rebuild_refs_for_pages(all_page_ids)
