"""FastAPI 应用入口"""

from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.config import load_config, get_config
from app.models.database import init_db_sync


@asynccontextmanager
async def lifespan(app: FastAPI):
    # 启动时：加载配置、初始化数据库
    load_config()
    init_db_sync()
    yield


app = FastAPI(
    title="Personal Wiki",
    description="PKM - 个人知识管理系统",
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


# 注册路由
from app.api import ingest, wiki, search  # noqa: E402

app.include_router(ingest.router, prefix="/api", tags=["ingest"])
app.include_router(wiki.router, prefix="/api/wiki", tags=["wiki"])
app.include_router(search.router, prefix="/api/search", tags=["search"])


@app.get("/api/health")
async def health():
    cfg = get_config()
    return {
        "status": "ok",
        "cloud_provider": cfg.llm.cloud_provider,
        "local_provider": cfg.llm.local_provider,
    }
