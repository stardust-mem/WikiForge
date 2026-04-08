"""Wiki 页面生成 — 根据分类和内容创建 Wiki 页面"""

import json
import re
from datetime import datetime
from pathlib import Path

from app.config import get_wiki_root
from app.llm.router import get_provider
from app.llm.prompts import WIKI_GENERATE_SYSTEM, WIKI_GENERATE_USER
from app.models.schemas import ClassificationResult


def _sanitize_filename(name: str) -> str:
    """将标题转为合法的文件名"""
    name = name.lower().strip()
    name = re.sub(r"[^\w\u4e00-\u9fff\-]", "-", name)
    name = re.sub(r"-+", "-", name)
    return name.strip("-")[:80]


def _write_wiki_page(category: str, filename: str, content: str) -> str:
    """写入 wiki 页面文件，返回 page_id"""
    wiki_root = get_wiki_root()
    cat_dir = wiki_root / category
    cat_dir.mkdir(parents=True, exist_ok=True)

    if not filename.endswith(".md"):
        filename = filename + ".md"

    file_path = cat_dir / filename
    file_path.write_text(content, encoding="utf-8")

    page_id = f"{category}/{Path(filename).stem}"
    return page_id


async def generate_wiki_pages(
    source_id: str,
    filename: str,
    content: str,
    classification: ClassificationResult,
) -> dict:
    """
    根据文档内容和分类结果生成 Wiki 页面。

    返回：
    {
        "pages_created": ["sources/xxx", "concepts/yyy", ...],
        "pages_updated": [],
    }
    """
    provider = get_provider("wiki_generate")

    # 限制内容长度避免 token 超限
    max_content_len = 8000
    truncated_content = content[:max_content_len]
    if len(content) > max_content_len:
        truncated_content += "\n\n[...内容已截断...]"

    result = await provider.chat_json(
        messages=[
            {"role": "system", "content": WIKI_GENERATE_SYSTEM},
            {
                "role": "user",
                "content": WIKI_GENERATE_USER.format(
                    filename=filename,
                    document_type=classification.document_type,
                    topic_tags=json.dumps(classification.topic_tags, ensure_ascii=False),
                    entities=json.dumps(classification.entities, ensure_ascii=False),
                    summary=classification.summary_one_line,
                    content=truncated_content,
                ),
            },
        ],
        max_tokens=8192,
    )

    pages_created = []
    now = datetime.now().strftime("%Y-%m-%d")

    # 1. 写入 source 页面
    source_page = result.get("source_page", {})
    if source_page:
        sp_filename = _sanitize_filename(
            source_page.get("filename", f"source-{source_id[:8]}")
        )
        sp_content = source_page.get("content", "")
        if not sp_content.startswith("---"):
            # 补充 frontmatter
            frontmatter = f"""---
title: "{source_page.get('title', filename)}"
category: "sources"
created_at: "{now}"
last_updated: "{now}"
source_refs:
  - source_id: "{source_id}"
    filename: "{filename}"
topic_tags: {json.dumps(classification.topic_tags, ensure_ascii=False)}
---

"""
            sp_content = frontmatter + sp_content

        page_id = _write_wiki_page("sources", sp_filename, sp_content)
        pages_created.append(page_id)

    # 2. 写入 concept 页面
    for cp in result.get("concept_pages", []):
        cp_filename = _sanitize_filename(
            cp.get("filename", cp.get("title", "concept"))
        )
        cp_content = cp.get("content", "")
        if not cp_content.startswith("---"):
            frontmatter = f"""---
title: "{cp.get('title', '')}"
category: "concepts"
created_at: "{now}"
last_updated: "{now}"
source_refs:
  - source_id: "{source_id}"
    filename: "{filename}"
topic_tags: {json.dumps(classification.topic_tags, ensure_ascii=False)}
---

"""
            cp_content = frontmatter + cp_content

        page_id = _write_wiki_page("concepts", cp_filename, cp_content)
        pages_created.append(page_id)

    # 3. 写入 entity 页面
    for ep in result.get("entity_pages", []):
        ep_filename = _sanitize_filename(
            ep.get("filename", ep.get("title", "entity"))
        )
        ep_content = ep.get("content", "")
        if not ep_content.startswith("---"):
            frontmatter = f"""---
title: "{ep.get('title', '')}"
category: "entities"
created_at: "{now}"
last_updated: "{now}"
source_refs:
  - source_id: "{source_id}"
    filename: "{filename}"
topic_tags: {json.dumps(classification.topic_tags, ensure_ascii=False)}
---

"""
            ep_content = frontmatter + ep_content

        page_id = _write_wiki_page("entities", ep_filename, ep_content)
        pages_created.append(page_id)

    return {
        "pages_created": pages_created,
        "pages_updated": [],
    }
