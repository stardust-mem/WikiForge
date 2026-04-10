"""topics/ 主题聚合页维护 — LLM 生成核心观点摘要"""

import json
import re
from datetime import datetime
from pathlib import Path

from app.config import get_wiki_root


def _find_related_pages(tag: str, wiki_root: Path) -> dict[str, list[str]]:
    """扫描 wiki 中与该主题相关的概念页和实体页"""
    related = {"concepts": [], "entities": [], "sources": []}
    for category in related:
        cat_dir = wiki_root / category
        if not cat_dir.exists():
            continue
        for md_file in cat_dir.glob("*.md"):
            content = md_file.read_text(encoding="utf-8")
            # 检查 topic_tags 是否包含该主题
            if tag.lower() in content.lower():
                page_id = f"{category}/{md_file.stem}"
                related[category].append(page_id)
    return related


async def generate_topic_summary(
    tag: str,
    related_pages: dict[str, list[str]],
    wiki_root: Path,
) -> str:
    """用 LLM 生成主题的核心观点摘要"""
    from app.llm.router import get_provider

    # 收集相关页面的内容摘要
    context_parts = []
    for category, page_ids in related_pages.items():
        for page_id in page_ids[:5]:  # 每类最多5个避免太长
            parts = page_id.split("/", 1)
            if len(parts) == 2:
                file_path = wiki_root / parts[0] / f"{parts[1]}.md"
                if file_path.exists():
                    content = file_path.read_text(encoding="utf-8")
                    # 去 frontmatter，取前 1500 字符
                    if content.startswith("---"):
                        end = content.find("---", 3)
                        if end > 0:
                            content = content[end + 3:].strip()
                    context_parts.append(f"[{page_id}]\n{content[:1500]}")

    if not context_parts:
        return ""

    context = "\n\n---\n\n".join(context_parts)

    provider = get_provider("summarize")
    prompt = f"""根据以下 Wiki 页面内容，为「{tag}」这个主题生成一段核心观点摘要。

要求：
1. 用 3-5 个要点概括当前知识库对这个主题的主要认知
2. 每个要点一句话，简洁有力
3. 只基于提供的内容，不要编造

页面内容：
{context}

直接输出要点列表（不需要标题），格式：
1. 要点一
2. 要点二
..."""

    try:
        summary = await provider.chat(
            messages=[{"role": "user", "content": prompt}],
            max_tokens=1024,
        )
        return summary.strip()
    except Exception:
        return ""


async def update_topic_pages(
    topic_tags: list[str],
    source_page_id: str,
    source_filename: str,
    summary: str,
) -> list[str]:
    """
    为每个 topic_tag 更新或创建主题聚合页。
    新建时用 LLM 生成核心观点摘要。

    返回更新的 page_id 列表。
    """
    wiki_root = get_wiki_root()
    topics_dir = wiki_root / "topics"
    topics_dir.mkdir(parents=True, exist_ok=True)
    now = datetime.now().strftime("%Y-%m-%d")

    updated = []

    for tag in topic_tags:
        safe_name = tag.replace(" ", "-").replace("/", "-").lower()
        topic_file = topics_dir / f"{safe_name}.md"

        if topic_file.exists():
            # 追加新文档引用
            content = topic_file.read_text(encoding="utf-8")
            new_entry = f"- {now}: [[{source_page_id}]] — {summary}"

            if "## 近期新增文档" in content:
                content = content.replace(
                    "## 近期新增文档",
                    f"## 近期新增文档\n{new_entry}",
                )
            else:
                content += f"\n\n## 近期新增文档\n{new_entry}\n"

            topic_file.write_text(content, encoding="utf-8")
        else:
            # 查找相关页面
            related = _find_related_pages(tag, wiki_root)

            # 生成核心观点摘要
            topic_summary = await generate_topic_summary(tag, related, wiki_root)

            # 构建相关概念和实体列表
            concepts_list = "\n".join(
                f"- [[{pid}]]" for pid in related["concepts"]
            ) or "_暂无_"
            entities_list = "\n".join(
                f"- [[{pid}]]" for pid in related["entities"]
            ) or "_暂无_"

            summary_section = ""
            if topic_summary:
                summary_section = f"""
## 核心观点摘要

{topic_summary}
"""

            content = f"""---
title: "{tag}"
category: "topics"
created_at: "{now}"
last_updated: "{now}"
---

# {tag}

> 本主题最近更新：{now}
{summary_section}
## 相关概念

{concepts_list}

## 相关实体

{entities_list}

## 文档来源

- {now}: [[{source_page_id}]] — {summary}

## 近期新增文档
"""
            topic_file.write_text(content, encoding="utf-8")

        updated.append(f"topics/{safe_name}")

    return updated


def cleanup_topic_references(deleted_page_ids: list[str], source_id: str) -> list[str]:
    """从 topics/*.md 中移除对已删除页面的引用。"""
    wiki_root = get_wiki_root()
    topics_dir = wiki_root / "topics"
    if not topics_dir.exists():
        return []

    modified = []
    for topic_file in list(topics_dir.glob("*.md")):
        content = topic_file.read_text(encoding="utf-8")
        original = content

        lines = content.split("\n")
        filtered = []
        for line in lines:
            should_remove = False
            for pid in deleted_page_ids:
                if f"[[{pid}]]" in line:
                    should_remove = True
                    break
            if not should_remove:
                filtered.append(line)

        content = "\n".join(filtered)
        if content != original:
            has_refs = "[[" in content.split("---", 2)[-1] if content.count("---") >= 2 else "[[" in content
            if not has_refs:
                topic_file.unlink()
            else:
                topic_file.write_text(content, encoding="utf-8")
            modified.append(f"topics/{topic_file.stem}")

    return modified
