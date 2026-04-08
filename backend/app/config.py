"""应用配置管理 — 从 config.yaml 加载"""

from pathlib import Path
from typing import Optional

import yaml
from pydantic import BaseModel


class LLMConfig(BaseModel):
    cloud_provider: str = "minimax"
    cloud_model: str = "MiniMax-M2.7"
    cloud_api_key: str = ""
    cloud_base_url: str = "https://api.minimaxi.com/v1"

    local_provider: str = "minimax"
    local_model: str = "MiniMax-M2.7"
    local_api_key: str = ""
    local_base_url: str = "https://api.minimaxi.com/v1"

    vision_provider: str = "claude"
    vision_model: str = "claude-sonnet-4-6"
    vision_api_key: str = ""

    embedding_model: str = "BAAI/bge-small-zh-v1.5"


class PathsConfig(BaseModel):
    wiki_root: str = "wiki-root"
    database: str = "data/wiki.db"
    uploads: str = "data/uploads"


class ServerConfig(BaseModel):
    host: str = "0.0.0.0"
    port: int = 8000


class AppConfig(BaseModel):
    llm: LLMConfig = LLMConfig()
    paths: PathsConfig = PathsConfig()
    server: ServerConfig = ServerConfig()


_config: Optional[AppConfig] = None
BASE_DIR = Path(__file__).resolve().parent.parent  # backend/


def load_config(config_path: Optional[Path] = None) -> AppConfig:
    global _config
    if config_path is None:
        config_path = BASE_DIR / "config.yaml"
    if config_path.exists():
        with open(config_path) as f:
            data = yaml.safe_load(f) or {}
        _config = AppConfig(**data)
    else:
        _config = AppConfig()
    return _config


def get_config() -> AppConfig:
    if _config is None:
        return load_config()
    return _config


def get_wiki_root() -> Path:
    return BASE_DIR / get_config().paths.wiki_root


def get_db_path() -> Path:
    return BASE_DIR / get_config().paths.database


def get_uploads_dir() -> Path:
    return BASE_DIR / get_config().paths.uploads
