"""topics/ 主题聚合页维护"""

import json
from datetime import datetime
from pathlib import Path

from app.config import get_wiki_root


def update_topic_pages(
    topic_tags: list[str],
    source_page_id: str,
    source_filename: str,
    summary: str,
) -> list[str]:
    """
    为每个 topic_tag 更新或创建主题聚合页。

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
            # 创建新主题页
            content = f"""---
title: "{tag}"
category: "topics"
created_at: "{now}"
last_updated: "{now}"
---

# {tag}

> 本主题最近更新：{now}

## 相关文档
- {now}: [[{source_page_id}]] — {summary}

## 近期新增文档
"""
            topic_file.write_text(content, encoding="utf-8")

        updated.append(f"topics/{safe_name}")

    return updated
