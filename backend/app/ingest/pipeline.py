"""Ingest Pipeline — 主流程编排"""

import json
import uuid
from datetime import datetime
from pathlib import Path

from app.models.database import get_db
from app.models.schemas import IngestResponse
from app.ingest.classifier import classify_document
from app.ingest.segmenter import segment_document
from app.ingest.vision import describe_image
from app.wiki.generator import generate_wiki_pages
from app.wiki.index import rebuild_index
from app.wiki.topics import update_topic_pages


def _detect_file_type(file_path: Path) -> str:
    suffix = file_path.suffix.lower()
    mapping = {
        ".pdf": "pdf",
        ".docx": "docx",
        ".doc": "docx",
        ".pptx": "pptx",
        ".ppt": "pptx",
        ".md": "md",
        ".txt": "txt",
    }
    return mapping.get(suffix, "txt")


async def _extract_text(file_path: Path, file_type: str) -> tuple[str, list[dict], list[tuple[bytes, str]]]:
    """
    提取文本 + headings + 图片列表。
    返回: (text, headings, [(image_bytes, media_type), ...])
    """
    headings = []
    images = []

    if file_type == "pdf":
        from app.ingest.extractors.pdf import extract_pdf
        result = extract_pdf(file_path)
        text = result.total_text
        for page in result.pages:
            for img_bytes, img_type in zip(page.images, page.image_types):
                images.append((img_bytes, img_type))
    elif file_type == "docx":
        from app.ingest.extractors.docx import extract_docx
        result = extract_docx(file_path)
        text = result.text
        headings = result.headings
        for img_bytes, img_type in zip(result.images, result.image_types):
            images.append((img_bytes, img_type))
        # 追加表格到文本
        if result.tables:
            text += "\n\n" + "\n\n".join(result.tables)
    elif file_type == "pptx":
        from app.ingest.extractors.pptx import extract_pptx
        result = extract_pptx(file_path)
        text = result.total_text
        for slide in result.slides:
            for img_bytes, img_type in zip(slide.images, slide.image_types):
                images.append((img_bytes, img_type))
    else:
        from app.ingest.extractors.markdown import extract_markdown
        result = extract_markdown(file_path)
        text = result.text
        headings = result.headings

    return text, headings, images


async def _process_images(images: list[tuple[bytes, str]]) -> list[str]:
    """用 Vision API 描述所有图片"""
    descriptions = []
    for img_bytes, media_type in images:
        try:
            desc = await describe_image(img_bytes, media_type)
            descriptions.append(desc)
        except Exception as e:
            descriptions.append(f"[图片描述失败: {e}]")
    return descriptions


async def run_ingest_pipeline(
    file_path: Path,
    content_hash: str,
) -> IngestResponse:
    """
    完整的 Ingest Pipeline：
    1. 格式识别 & 文本提取
    2. SHA256 去重检查
    3. 图片 Vision 描述
    4. 智能分段
    5. 自动分类
    6. Wiki 页面生成
    7. 主题聚合页更新
    8. index.md 重建
    9. 写入数据库
    """
    source_id = str(uuid.uuid4())[:12]
    filename = file_path.name
    file_type = _detect_file_type(file_path)

    # 1. 去重检查
    db = await get_db()
    try:
        row = await db.execute(
            "SELECT source_id FROM sources WHERE content_hash = ?",
            (content_hash,),
        )
        existing = await row.fetchone()
        if existing:
            await db.close()
            return IngestResponse(
                source_id=existing["source_id"],
                filename=filename,
                document_type="duplicate",
                topic_tags=[],
                summary=f"文档已存在（hash: {content_hash[:16]}...）",
                wiki_pages_created=[],
                wiki_pages_updated=[],
            )
    finally:
        await db.close()

    # 2. 文本提取
    text, headings, images = await _extract_text(file_path, file_type)

    # 3. 图片描述（如有图片）
    image_descriptions = []
    if images:
        image_descriptions = await _process_images(images)
        # 将图片描述追加到文本
        if image_descriptions:
            desc_text = "\n\n## 图片内容\n\n" + "\n\n".join(
                f"**图片{i+1}**：{desc}"
                for i, desc in enumerate(image_descriptions)
            )
            text += desc_text

    # 4. 自动分类
    classification = await classify_document(filename, text)

    # 5. 智能分段（暂存，后续 Phase 3 用于嵌入）
    segments = await segment_document(text, headings)

    # 6. Wiki 页面生成
    wiki_result = await generate_wiki_pages(
        source_id=source_id,
        filename=filename,
        content=text,
        classification=classification,
    )

    # 7. 主题聚合页更新
    source_page_id = (
        wiki_result["pages_created"][0] if wiki_result["pages_created"] else ""
    )
    topic_updates = update_topic_pages(
        topic_tags=classification.topic_tags,
        source_page_id=source_page_id,
        source_filename=filename,
        summary=classification.summary_one_line,
    )

    # 8. 重建 index.md
    rebuild_index()

    # 9. 写入数据库
    db = await get_db()
    try:
        await db.execute(
            """INSERT INTO sources
               (source_id, filename, file_type, content_hash, document_type,
                topic_tags, language, word_count, summary_one_line)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                source_id,
                filename,
                file_type,
                content_hash,
                classification.document_type,
                json.dumps(classification.topic_tags, ensure_ascii=False),
                classification.language,
                len(text),
                classification.summary_one_line,
            ),
        )

        # 写入 wiki_pages 表
        for page_id in wiki_result["pages_created"]:
            parts = page_id.split("/")
            category = parts[0]
            title = parts[1].replace("-", " ") if len(parts) > 1 else page_id
            await db.execute(
                """INSERT OR REPLACE INTO wiki_pages
                   (page_id, title, category, source_count)
                   VALUES (?, ?, ?, 1)""",
                (page_id, title, category),
            )
            await db.execute(
                """INSERT OR IGNORE INTO source_page_map (source_id, page_id)
                   VALUES (?, ?)""",
                (source_id, page_id),
            )

        # 写入分段缓存
        for i, seg in enumerate(segments):
            await db.execute(
                """INSERT INTO segments
                   (segment_id, source_id, segment_index, title, summary,
                    content, token_count, parent_segment_id)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    seg.segment_id,
                    source_id,
                    i,
                    seg.title,
                    seg.summary,
                    seg.content,
                    seg.token_count,
                    seg.parent_segment_id,
                ),
            )

        # 操作日志
        await db.execute(
            """INSERT INTO operation_log (op_type, target_id, detail)
               VALUES ('ingest', ?, ?)""",
            (
                source_id,
                json.dumps({
                    "filename": filename,
                    "file_type": file_type,
                    "document_type": classification.document_type,
                    "pages_created": wiki_result["pages_created"],
                    "segments": len(segments),
                }, ensure_ascii=False),
            ),
        )

        await db.commit()
    finally:
        await db.close()

    return IngestResponse(
        source_id=source_id,
        filename=filename,
        document_type=classification.document_type,
        topic_tags=classification.topic_tags,
        summary=classification.summary_one_line,
        wiki_pages_created=wiki_result["pages_created"],
        wiki_pages_updated=topic_updates,
    )
