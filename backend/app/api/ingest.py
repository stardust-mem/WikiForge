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

    # 保存上传文件
    uploads_dir = get_uploads_dir()
    uploads_dir.mkdir(parents=True, exist_ok=True)
    file_path = uploads_dir / file.filename

    content = await file.read()
    content_hash = hashlib.sha256(content).hexdigest()

    with open(file_path, "wb") as f:
        f.write(content)

    # 创建任务，后台执行
    task_id = str(uuid.uuid4())[:12]
    create_task(task_id, file.filename)
    asyncio.create_task(_run_pipeline_background(task_id, file_path, content_hash))

    return {"task_id": task_id, "filename": file.filename, "status": "pending"}


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
    finally:
        await db.close()

    results = []
    for row in rows:
        source_id = row[0]
        db2 = await get_db()
        try:
            page_rows = await db2.execute_fetchall(
                "SELECT page_id FROM source_page_map WHERE source_id = ?",
                (source_id,),
            )
        finally:
            await db2.close()

        pages_created = [r[0] for r in page_rows]
        topic_tags = json.loads(row[3]) if row[3] else []

        results.append({
            "source_id": source_id,
            "filename": row[1],
            "document_type": row[2] or "unknown",
            "topic_tags": topic_tags,
            "summary": row[4] or "",
            "wiki_pages_created": pages_created,
            "wiki_pages_updated": [],
        })

    return results
