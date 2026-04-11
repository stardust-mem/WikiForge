"""FastAPI 应用入口"""

from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse

from app.config import load_config, get_config, BASE_DIR
from app.models.database import init_db_sync


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时：加载配置、初始化数据库
    load_config()
    init_db_sync()
    yield


app = FastAPI(
    title="NEWTYPE",
    description="NEWTYPE - 个人知识管理系统",
    version="0.1.0",
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


# 注册 API 路由
from app.api import ingest, wiki, search, lint  # noqa: E402

app.include_router(ingest.router, prefix="/api", tags=["ingest"])
app.include_router(wiki.router, prefix="/api/wiki", tags=["wiki"])
app.include_router(search.router, prefix="/api/search", tags=["search"])
app.include_router(lint.router, prefix="/api/lint", tags=["lint"])


@app.get("/api/health")
async def health():
    cfg = get_config()
    return {
        "status": "ok",
        "cloud_provider": cfg.llm.cloud_provider,
        "local_provider": cfg.llm.local_provider,
    }


# Serve 前端静态文件（production 模式）
# npm run build 后产物在 frontend/dist/
FRONTEND_DIST = BASE_DIR.parent / "frontend" / "dist"
if FRONTEND_DIST.exists():
    app.mount("/assets", StaticFiles(directory=FRONTEND_DIST / "assets"), name="assets")

    @app.get("/{full_path:path}")
    async def serve_spa(full_path: str):
        """所有非 /api 请求返回 index.html（SPA fallback）"""
        file_path = FRONTEND_DIST / full_path
        if file_path.is_file():
            return FileResponse(file_path)
        return FileResponse(FRONTEND_DIST / "index.html")
