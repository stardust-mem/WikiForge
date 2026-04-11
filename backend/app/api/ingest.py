"""文件上传 & Ingest API — 异步任务模式"""

import asyncio
import hashlib
import traceback
import uuid
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException

from app.config import get_uploads_dir, get_config
from app.models.database import get_db
from app.ingest.tasks import (
    create_task, get_task, get_all_tasks,
    complete_task, fail_task, TaskStatus,
)
import json

router = APIRouter()

SUPPORTED_TYPES = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".md", ".txt"}


async def _run_pipeline_background(task_id: str, file_path: Path, content_hash: str):
    """后台执行 pipeline，更新任务状态"""
    from app.ingest.pipeline import run_ingest_pipeline
    try:
        result = await run_ingest_pipeline(file_path, content_hash, task_id=task_id)
        complete_task(task_id, {
            "source_id": result.source_id,
            "filename": result.filename,
            "document_type": result.document_type,
            "topic_tags": result.topic_tags,
            "summary": result.summary,
            "wiki_pages_created": result.wiki_pages_created,
            "wiki_pages_updated": result.wiki_pages_updated,
        })
    except Exception as e:
        traceback.print_exc()
        fail_task(task_id, str(e))


@router.post("/ingest")
async def ingest_file(file: UploadFile = File(...)):
    """上传文件，立即返回 task_id，后台异步处理"""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_TYPES:
        raise HTTPException(400, f"不支持的文件类型: {suffix}")

    cfg = get_config()
    if not cfg.llm.cloud_api_key and not cfg.llm.local_api_key:
        raise HTTPException(
            500,
            "未配置 LLM API key。请编辑 backend/config.yaml 填入 cloud_api_key，"
            "或设置环境变量 MINIMAX_API_KEY",
        )

    # 保存上传文件（sanitize filename to prevent path traversal）
    safe_filename = Path(file.filename).name.replace("/", "_").replace("\\", "_")
    if not safe_filename:
        raise HTTPException(400, "无效的文件名")
    uploads_dir = get_uploads_dir()
    uploads_dir.mkdir(parents=True, exist_ok=True)
    file_path = uploads_dir / safe_filename

    content = await file.read()
    content_hash = hashlib.sha256(content).hexdigest()

    # 前置去重检查：相同内容的文件直接返回，不启动后台任务
    db = await get_db()
    try:
        row = await db.execute(
            "SELECT source_id, filename FROM sources WHERE content_hash = ?",
            (content_hash,),
        )
        existing = await row.fetchone()
    finally:
        await db.close()

    if existing:
        return {
            "task_id": "",
            "filename": safe_filename,
            "status": "duplicate",
            "existing_filename": existing["filename"],
        }

    with open(file_path, "wb") as f:
        f.write(content)

    # 创建任务，后台执行
    task_id = str(uuid.uuid4())[:12]
    create_task(task_id, safe_filename)
    asyncio.create_task(_run_pipeline_background(task_id, file_path, content_hash))

    return {"task_id": task_id, "filename": safe_filename, "status": "pending"}


@router.get("/ingest/status/{task_id}")
async def get_ingest_status(task_id: str):
    """查询任务状态"""
    task = get_task(task_id)
    if not task:
        raise HTTPException(404, "任务不存在")
    return {
        "task_id": task.task_id,
        "filename": task.filename,
        "status": task.status.value,
        "progress_label": task.progress_label,
        "error": task.error,
        "result": task.result,
    }


@router.get("/ingest/tasks")
async def list_ingest_tasks():
    """列出所有正在进行的任务"""
    tasks = get_all_tasks()
    return [
        {
            "task_id": t.task_id,
            "filename": t.filename,
            "status": t.status.value,
            "progress_label": t.progress_label,
            "error": t.error,
            "result": t.result,
        }
        for t in tasks
    ]


@router.delete("/ingest/{source_id}")
async def delete_source(source_id: str):
    """删除一个已导入的文档及其生成的 Wiki 内容"""
    db = await get_db()
    try:
        # 1. 查找 source 是否存在
        row = await db.execute(
            "SELECT source_id, filename FROM sources WHERE source_id = ?",
            (source_id,),
        )
        source = await row.fetchone()
        if not source:
            raise HTTPException(404, f"文档不存在: {source_id}")
        filename = source["filename"]

        # 2. 找到该 source 关联的所有 wiki 页面
        page_rows = await db.execute_fetchall(
            "SELECT page_id FROM source_page_map WHERE source_id = ?",
            (source_id,),
        )
        page_ids = [r[0] for r in page_rows]

        # 3. 区分独占页面 vs 共享页面
        exclusive_pages = []
        shared_pages = []
        for page_id in page_ids:
            cnt_row = await db.execute(
                "SELECT COUNT(*) FROM source_page_map WHERE page_id = ?",
                (page_id,),
            )
            cnt = (await cnt_row.fetchone())[0]
            if cnt <= 1:
                exclusive_pages.append(page_id)
            else:
                shared_pages.append(page_id)

        # 4. 删除独占页面的所有关联记录
        for page_id in exclusive_pages:
            await db.execute("DELETE FROM wiki_fts WHERE page_id = ?", (page_id,))
            await db.execute("DELETE FROM page_embeddings WHERE page_id = ?", (page_id,))
            await db.execute(
                "DELETE FROM page_refs WHERE from_page_id = ? OR to_page_id = ?",
                (page_id, page_id),
            )
            await db.execute("DELETE FROM wiki_pages WHERE page_id = ?", (page_id,))

        # 5. 共享页面：递减 source_count
        for page_id in shared_pages:
            await db.execute(
                "UPDATE wiki_pages SET source_count = MAX(source_count - 1, 0) WHERE page_id = ?",
                (page_id,),
            )

        # 6. 删除 source_page_map、segments、source 本身
        await db.execute("DELETE FROM source_page_map WHERE source_id = ?", (source_id,))
        await db.execute("DELETE FROM segments WHERE source_id = ?", (source_id,))
        await db.execute("DELETE FROM sources WHERE source_id = ?", (source_id,))

        # 7. 操作日志
        await db.execute(
            """INSERT INTO operation_log (op_type, target_id, detail)
               VALUES ('delete', ?, ?)""",
            (source_id, json.dumps({
                "filename": filename,
                "exclusive_pages_deleted": exclusive_pages,
                "shared_pages_kept": shared_pages,
            }, ensure_ascii=False)),
        )

        await db.commit()
    finally:
        await db.close()

    # 8. 删除独占页面的 wiki 文件
    from app.config import get_wiki_root
    wiki_root = get_wiki_root()
    deleted_files = []
    for page_id in exclusive_pages:
        parts = page_id.split("/", 1)
        if len(parts) == 2:
            file_path = wiki_root / parts[0] / f"{parts[1]}.md"
            if file_path.exists():
                file_path.unlink()
                deleted_files.append(str(file_path.relative_to(wiki_root)))

    # 9. 清理 topic 页面中的 stale 引用
    from app.wiki.topics import cleanup_topic_references
    cleanup_topic_references(exclusive_pages, source_id)

    # 10. 删除上传的原始文件
    uploads_dir = get_uploads_dir()
    upload_file = uploads_dir / filename
    if upload_file.exists():
        upload_file.unlink()

    # 11. 重建 index.md
    from app.wiki.index import rebuild_index
    rebuild_index()

    # 12. 追加操作日志
    from app.wiki.log import append_log
    append_log("delete", f"{filename} | 删除 {len(exclusive_pages)} 页, 保留共享 {len(shared_pages)} 页")

    # 13. Git 自动提交
    from app.wiki.git_ops import auto_commit
    auto_commit(f"delete: {filename} (删除 {len(exclusive_pages)} 页)")

    # 14. 重建 BM25 索引
    from app.search.bm25_index import build_bm25_index
    build_bm25_index()

    return {
        "source_id": source_id,
        "filename": filename,
        "pages_deleted": exclusive_pages,
        "pages_kept_shared": shared_pages,
    }


@router.get("/ingest/history")
async def get_ingest_history(limit: int = 20):
    """获取最近的导入记录（从数据库）"""
    db = await get_db()
    try:
        rows = await db.execute_fetchall(
            """SELECT source_id, filename, document_type, topic_tags,
                      summary_one_line, ingested_at
               FROM sources
               ORDER BY ingested_at DESC
               LIMIT ?""",
            (limit,),
        )

        # Batch-fetch all page mappings in a single query to avoid N+1
        source_ids = [row[0] for row in rows]
        page_map: dict[str, list[str]] = {sid: [] for sid in source_ids}
        if source_ids:
            placeholders = ",".join("?" for _ in source_ids)
            page_rows = await db.execute_fetchall(
                f"SELECT source_id, page_id FROM source_page_map WHERE source_id IN ({placeholders})",
                tuple(source_ids),
            )
            for pr in page_rows:
                page_map[pr[0]].append(pr[1])
    finally:
        await db.close()

    results = []
    for row in rows:
        source_id = row[0]
        topic_tags = json.loads(row[3]) if row[3] else []

        results.append({
            "source_id": source_id,
            "filename": row[1],
            "document_type": row[2] or "unknown",
            "topic_tags": topic_tags,
            "summary": row[4] or "",
            "wiki_pages_created": page_map.get(source_id, []),
            "wiki_pages_updated": [],
        })

    return results
