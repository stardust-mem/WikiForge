"""Wiki 健康检查 — 孤立页、悬空链接、过期页面、缺失实体"""

import re
from datetime import datetime, timedelta
from pathlib import Path

from app.config import get_wiki_root
from app.models.database import get_db

CATEGORIES = ["entities", "concepts", "topics", "sources"]
_WIKILINK_RE = re.compile(r"\[\[([^\]]+)\]\]")

# 时间敏感关键词
_TIME_SENSITIVE_WORDS = [
    "最新", "目前", "当前", "截至", "近期", "今年", "去年",
    "recently", "currently", "latest", "as of", "this year",
]


async def check_orphan_pages() -> list[dict]:
    """查找 0 个入链的页面（无其他页面引用它）"""
    db = await get_db()
    try:
        # 所有有 wiki 文件的页面
        wiki_root = get_wiki_root()
        all_pages: set[str] = set()
        for cat in CATEGORIES:
            cat_dir = wiki_root / cat
            if not cat_dir.exists():
                continue
            for md_file in cat_dir.glob("*.md"):
                all_pages.add(f"{cat}/{md_file.stem}")

        # 有入链的页面
        rows = await db.execute_fetchall(
            "SELECT DISTINCT to_page_id FROM page_refs"
        )
        linked_pages = {row[0] for row in rows}

        # index/topic 类的页面天然没有入链，排除 sources 分类
        orphans = []
        for pid in sorted(all_pages - linked_pages):
            if pid.startswith("sources/"):
                continue  # 文档来源页不算孤立
            orphans.append({
                "page_id": pid,
                "issue": "没有任何其他页面引用此页面",
            })
        return orphans
    finally:
        await db.close()


async def check_dangling_links() -> list[dict]:
    """查找悬空 wikilink（目标页面不存在）"""
    wiki_root = get_wiki_root()
    issues = []

    # 收集所有存在的页面 stem（用于模糊匹配）
    existing_stems: dict[str, str] = {}  # normalized_stem -> page_id
    for cat in CATEGORIES:
        cat_dir = wiki_root / cat
        if not cat_dir.exists():
            continue
        for md_file in cat_dir.glob("*.md"):
            stem = md_file.stem.lower().replace(" ", "-").replace("_", "-")
            existing_stems[stem] = f"{cat}/{md_file.stem}"

    for cat in CATEGORIES:
        cat_dir = wiki_root / cat
        if not cat_dir.exists():
            continue
        for md_file in cat_dir.glob("*.md"):
            page_id = f"{cat}/{md_file.stem}"
            content = md_file.read_text(encoding="utf-8")
            for match in _WIKILINK_RE.finditer(content):
                inner = match.group(1)
                target = inner.split("|")[0].strip()
                # 尝试解析
                norm = target.lower().replace(" ", "-").replace("_", "-")
                if norm in existing_stems:
                    continue
                # 尝试 category/name 格式
                if "/" in target:
                    parts = target.split("/", 1)
                    check_path = wiki_root / parts[0] / f"{parts[1]}.md"
                    if check_path.exists():
                        continue
                issues.append({
                    "page_id": page_id,
                    "target": target,
                    "issue": f"[[{target}]] 指向的页面不存在",
                })

    return issues


async def check_stale_pages(days: int = 180) -> list[dict]:
    """查找含时间敏感词且超过 N 天未更新的页面"""
    wiki_root = get_wiki_root()
    cutoff = datetime.now() - timedelta(days=days)
    issues = []

    for cat in CATEGORIES:
        cat_dir = wiki_root / cat
        if not cat_dir.exists():
            continue
        for md_file in cat_dir.glob("*.md"):
            mtime = datetime.fromtimestamp(md_file.stat().st_mtime)
            if mtime >= cutoff:
                continue
            content = md_file.read_text(encoding="utf-8").lower()
            matched_words = [
                w for w in _TIME_SENSITIVE_WORDS if w in content
            ]
            if matched_words:
                page_id = f"{cat}/{md_file.stem}"
                issues.append({
                    "page_id": page_id,
                    "last_modified": mtime.strftime("%Y-%m-%d"),
                    "sensitive_words": matched_words[:3],
                    "issue": f"含时间敏感词且已 {(datetime.now() - mtime).days} 天未更新",
                })

    return issues


async def check_missing_entities() -> list[dict]:
    """查找多个文档提到但没有对应 entity 页面的名称"""
    db = await get_db()
    try:
        wiki_root = get_wiki_root()

        # 收集已有的 entity 页面名称
        entity_dir = wiki_root / "entities"
        existing_entities: set[str] = set()
        if entity_dir.exists():
            for md_file in entity_dir.glob("*.md"):
                existing_entities.add(md_file.stem.lower().replace("-", " "))

        # 从 segments 中提取高频名称
        rows = await db.execute_fetchall(
            "SELECT content FROM segments"
        )

        # 简单的中文人名/组织名模式（2-4 字）+ 英文专有名词
        name_counts: dict[str, int] = {}
        name_pattern = re.compile(
            r"(?:[\u4e00-\u9fff]{2,4}(?:公司|集团|大学|学院|研究院|部队|军|师|旅|团))"
            r"|(?:[A-Z][a-z]+(?:\s+[A-Z][a-z]+)+)"
        )
        for row in rows:
            content = row[0] or ""
            for match in name_pattern.finditer(content):
                name = match.group().strip()
                name_lower = name.lower()
                if name_lower not in existing_entities:
                    name_counts[name] = name_counts.get(name, 0) + 1

        # 返回出现在 2+ 个 segment 中的名称
        issues = []
        for name, count in sorted(
            name_counts.items(), key=lambda x: -x[1]
        ):
            if count >= 2:
                issues.append({
                    "name": name,
                    "mention_count": count,
                    "issue": f"在 {count} 个文档段落中被提及，但没有对应的 entity 页面",
                })
        return issues[:20]  # 最多返回 20 个建议
    finally:
        await db.close()


async def run_full_lint() -> dict:
    """运行所有检查，返回汇总报告"""
    orphans = await check_orphan_pages()
    dangling = await check_dangling_links()
    stale = await check_stale_pages()
    missing = await check_missing_entities()

    return {
        "orphan_pages": orphans,
        "dangling_links": dangling,
        "stale_pages": stale,
        "missing_entities": missing,
        "summary": {
            "orphan_count": len(orphans),
            "dangling_count": len(dangling),
            "stale_count": len(stale),
            "missing_count": len(missing),
            "total_issues": len(orphans) + len(dangling) + len(stale) + len(missing),
        },
    }
