"""文件上传 & Ingest API"""

import hashlib
import shutil
from pathlib import Path

from fastapi import APIRouter, UploadFile, File, HTTPException

from app.config import get_uploads_dir
from app.models.schemas import IngestResponse

router = APIRouter()

SUPPORTED_TYPES = {".pdf", ".docx", ".doc", ".pptx", ".ppt", ".md", ".txt"}


@router.post("/ingest", response_model=IngestResponse)
async def ingest_file(file: UploadFile = File(...)):
    """上传文件并触发 ingest pipeline"""
    suffix = Path(file.filename).suffix.lower()
    if suffix not in SUPPORTED_TYPES:
        raise HTTPException(400, f"不支持的文件类型: {suffix}")

    # 保存上传文件
    uploads_dir = get_uploads_dir()
    uploads_dir.mkdir(parents=True, exist_ok=True)
    file_path = uploads_dir / file.filename

    content = await file.read()
    content_hash = hashlib.sha256(content).hexdigest()

    with open(file_path, "wb") as f:
        f.write(content)

    # 调用 ingest pipeline
    from app.ingest.pipeline import run_ingest_pipeline

    result = await run_ingest_pipeline(file_path, content_hash)
    return result
