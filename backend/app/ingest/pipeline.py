"""Ingest Pipeline — 主流程编排"""

import json
import uuid
from datetime import datetime
from pathlib import Path

from app.config import get_wiki_root
from app.models.database import get_db
from app.models.schemas import IngestResponse
from app.ingest.classifier import classify_document
from app.ingest.segmenter import segment_document
from app.ingest.vision import describe_image
from app.wiki.generator import generate_wiki_pages
from app.wiki.index import rebuild_index
from app.wiki.topics import update_topic_pages
from app.search.embeddings import store_embedding
from app.search.hybrid import index_page_fts


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
    task_id: str = "",
) -> IngestResponse:
    """
    完整的 Ingest Pipeline，每步更新任务状态。
    """
    from app.ingest.tasks import update_task_status, TaskStatus

    def _update(status: TaskStatus):
        if task_id:
            update_task_status(task_id, status)

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
    _update(TaskStatus.EXTRACTING)
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
    _update(TaskStatus.CLASSIFYING)
    classification = await classify_document(filename, text)

    # 5. 智能分段
    _update(TaskStatus.SEGMENTING)
    segments = await segment_document(text, headings)

    # 6. Wiki 页面生成（分段处理超长文档）
    _update(TaskStatus.GENERATING)

    # 合并所有段的结果
    all_pages_created: list[str] = []
    all_pages_updated: list[str] = []

    if len(segments) <= 1:
        # 短文档：整体处理
        wiki_result = await generate_wiki_pages(
            source_id=source_id,
            filename=filename,
            content=text,
            classification=classification,
        )
        all_pages_created = wiki_result["pages_created"]
        all_pages_updated = wiki_result["pages_updated"]
    else:
        # 长文档：逐段处理，每段独立生成 Wiki 页面
        seen_pages: set[str] = set()  # 跟踪本轮已处理的页面
        for i, seg in enumerate(segments):
            seg_label = seg.title or f"第{i+1}段"
            seg_content = seg.content
            if seg.title:
                seg_content = f"## {seg.title}\n\n{seg_content}"
            if seg.summary:
                seg_content = f"> 段落摘要：{seg.summary}\n\n{seg_content}"

            try:
                seg_result = await generate_wiki_pages(
                    source_id=source_id,
                    filename=filename,  # 保留原始文件名，不加段落后缀
                    content=seg_content,
                    classification=classification,
                )
                # 合并结果：同一轮 ingest 中首次出现算 created，不降级为 updated
                for pid in seg_result["pages_created"]:
                    if pid not in seen_pages:
                        all_pages_created.append(pid)
                        seen_pages.add(pid)
                for pid in seg_result["pages_updated"]:
                    if pid not in seen_pages:
                        all_pages_updated.append(pid)
                        seen_pages.add(pid)
            except Exception as e:
                import logging
                logging.getLogger(__name__).warning(
                    f"段落 {seg_label} Wiki 生成失败: {e}"
                )
                continue

    wiki_result = {
        "pages_created": all_pages_created,
        "pages_updated": all_pages_updated,
    }

    # 7. 主题聚合页更新（skip if no pages were affected to avoid broken [[]] wikilinks）
    all_affected = wiki_result["pages_created"] + wiki_result["pages_updated"]
    topic_updates = []
    if all_affected:
        source_page_id = all_affected[0]
        topic_updates = await update_topic_pages(
            topic_tags=classification.topic_tags,
            source_page_id=source_page_id,
            source_filename=filename,
            summary=classification.summary_one_line,
        )

    # 8. 重建 index.md
    rebuild_index()

    # 9. 构建搜索索引（FTS5 + 嵌入向量）— 新建和更新的页面都需要重建索引
    _update(TaskStatus.INDEXING)
    wiki_root_path = get_wiki_root()
    for page_id in all_affected:
        parts = page_id.split("/", 1)
        if len(parts) == 2:
            file_path_wiki = wiki_root_path / parts[0] / f"{parts[1]}.md"
            if file_path_wiki.exists():
                page_content = file_path_wiki.read_text(encoding="utf-8")
                page_title = parts[1].replace("-", " ")
                # FTS5 索引
                await index_page_fts(page_id, page_title, page_content)
                # 嵌入向量
                await store_embedding(page_id, page_content[:2000])

    # 10. 写入数据库
    _update(TaskStatus.SAVING)
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

        # 写入 wiki_pages 表 — 新建页面
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

        # 更新 wiki_pages 表 — 已有页面追加来源
        for page_id in wiki_result["pages_updated"]:
            await db.execute(
                """UPDATE wiki_pages
                   SET source_count = source_count + 1
                   WHERE page_id = ?""",
                (page_id,),
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
                    "pages_updated": wiki_result["pages_updated"],
                    "segments": len(segments),
                }, ensure_ascii=False),
            ),
        )

        await db.commit()
    finally:
        await db.close()

    # 11. 追加操作日志
    from app.wiki.log import append_log
    pages_summary = f"创建 {len(wiki_result['pages_created'])} 页, 更新 {len(wiki_result['pages_updated'])} 页"
    append_log("ingest", f"{filename} | {classification.document_type} | {pages_summary}")

    # 12. Git 自动提交
    from app.wiki.git_ops import auto_commit
    auto_commit(f"ingest: {filename} ({pages_summary})")

    # 13. 重建 BM25 索引
    from app.search.bm25_index import build_bm25_index
    build_bm25_index()

    # Combine wiki pages that were merged with topic page updates
    all_updated = wiki_result["pages_updated"] + topic_updates

    return IngestResponse(
        source_id=source_id,
        filename=filename,
        document_type=classification.document_type,
        topic_tags=classification.topic_tags,
        summary=classification.summary_one_line,
        wiki_pages_created=wiki_result["pages_created"],
        wiki_pages_updated=all_updated,
    )
