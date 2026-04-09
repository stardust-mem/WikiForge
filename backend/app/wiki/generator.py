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


def _strip_frontmatter(content: str) -> tuple[str, str]:
    """Split content into (frontmatter_block, body).

    If content starts with '---', returns the full frontmatter block
    (including delimiters) and the remaining body.
    Otherwise returns ('', content).
    """
    if not content.startswith("---"):
        return "", content
    end = content.find("---", 3)
    if end == -1:
        return "", content
    # end points to the opening of the closing '---'
    end_of_fm = content.index("\n", end) + 1 if "\n" in content[end:] else end + 3
    return content[:end_of_fm], content[end_of_fm:]


def _write_wiki_page(
    category: str,
    filename: str,
    content: str,
    source_id: str = "",
    source_filename: str = "",
) -> tuple[str, bool]:
    """写入 wiki 页面文件，返回 (page_id, is_new)。

    如果文件已存在，将新内容以补充来源的形式追加而非覆盖。
    """
    wiki_root = get_wiki_root()
    cat_dir = wiki_root / category
    cat_dir.mkdir(parents=True, exist_ok=True)

    if not filename.endswith(".md"):
        filename = filename + ".md"

    file_path = cat_dir / filename
    page_id = f"{category}/{Path(filename).stem}"

    if file_path.exists():
        existing = file_path.read_text(encoding="utf-8")
        # Extract only the body from the new content (skip its frontmatter)
        _fm, new_body = _strip_frontmatter(content)
        now = datetime.now().strftime("%Y-%m-%d")
        merge_header = (
            f"\n\n---\n\n## 补充来源: {source_filename} ({now})\n\n"
        )
        merged = existing.rstrip("\n") + merge_header + new_body.lstrip("\n")
        file_path.write_text(merged, encoding="utf-8")
        return page_id, False  # updated, not new
    else:
        file_path.write_text(content, encoding="utf-8")
        return page_id, True  # brand new page


async def generate_wiki_pages(
    source_id: str,
    filename: str,
    content: str,
    classification: ClassificationResult,
) -> dict:
    """
    根据文档内容和分类结果生成 Wiki 页面。

    读取 CLAUDE.md 和 index.md 提供给 LLM 作为上下文，使其了解 wiki 规范和已有页面。
    LLM 返回新页面以及对已有页面的更新列表。

    如果目标页面已存在，会将新内容合并追加而非覆盖。

    返回：
    {
        "pages_created": ["sources/xxx", "concepts/yyy", ...],  # 全新页面
        "pages_updated": ["concepts/zzz", ...],                 # 已有页面被追加/更新
    }
    """
    provider = get_provider("wiki_generate")
    wiki_root = get_wiki_root()

    # --- Read wiki context files ---
    claude_md_path = wiki_root / "CLAUDE.md"
    claude_md_content = ""
    if claude_md_path.exists():
        claude_md_content = claude_md_path.read_text(encoding="utf-8")

    index_md_path = wiki_root / "index.md"
    index_content = ""
    if index_md_path.exists():
        index_content = index_md_path.read_text(encoding="utf-8")

    # 限制内容长度避免 token 超限
    max_content_len = 8000
    truncated_content = content[:max_content_len]
    if len(content) > max_content_len:
        truncated_content += "\n\n[...内容已截断...]"

    system_prompt = WIKI_GENERATE_SYSTEM.format(
        claude_md_content=claude_md_content,
        schema="see below",
    )

    user_prompt = WIKI_GENERATE_USER.format(
        index_content=index_content if index_content else "(empty wiki — no pages yet)",
        filename=filename,
        document_type=classification.document_type,
        topic_tags=json.dumps(classification.topic_tags, ensure_ascii=False),
        entities=json.dumps(classification.entities, ensure_ascii=False),
        summary=classification.summary_one_line,
        content=truncated_content,
    )

    result = await provider.chat_json(
        messages=[
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt},
        ],
        max_tokens=16384,
    )

    pages_created: list[str] = []
    pages_updated: list[str] = []
    now = datetime.now().strftime("%Y-%m-%d")

    def _record(page_id: str, is_new: bool) -> None:
        if is_new:
            pages_created.append(page_id)
        else:
            pages_updated.append(page_id)

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
source_count: 1
topic_tags: {json.dumps(classification.topic_tags, ensure_ascii=False)}
---

"""
            sp_content = frontmatter + sp_content

        page_id, is_new = _write_wiki_page(
            "sources", sp_filename, sp_content,
            source_id=source_id, source_filename=filename,
        )
        _record(page_id, is_new)

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
source_count: 1
topic_tags: {json.dumps(classification.topic_tags, ensure_ascii=False)}
---

"""
            cp_content = frontmatter + cp_content

        page_id, is_new = _write_wiki_page(
            "concepts", cp_filename, cp_content,
            source_id=source_id, source_filename=filename,
        )
        _record(page_id, is_new)

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
source_count: 1
topic_tags: {json.dumps(classification.topic_tags, ensure_ascii=False)}
---

"""
            ep_content = frontmatter + ep_content

        page_id, is_new = _write_wiki_page(
            "entities", ep_filename, ep_content,
            source_id=source_id, source_filename=filename,
        )
        _record(page_id, is_new)

    # 4. Process updates to existing pages from LLM output
    for update in result.get("updates", []):
        page_id = update.get("page_id", "")
        new_content = update.get("new_content", "")
        if not page_id or not new_content:
            continue
        # page_id is like "concepts/existing-page"
        page_path = wiki_root / (page_id + ".md")
        if page_path.exists():
            page_path.write_text(new_content, encoding="utf-8")
            pages_updated.append(page_id)

    return {
        "pages_created": pages_created,
        "pages_updated": pages_updated,
    }
