"""SQLite 数据库初始化与连接管理"""

import sqlite3
from pathlib import Path
from typing import Optional

import aiosqlite

from app.config import get_db_path

_DB_PATH: Optional[Path] = None


def _get_db_path() -> Path:
    global _DB_PATH
    if _DB_PATH is None:
        _DB_PATH = get_db_path()
        _DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return _DB_PATH


SCHEMA_SQL = """
-- 原始文档
CREATE TABLE IF NOT EXISTS sources (
    source_id       TEXT PRIMARY KEY,
    filename        TEXT NOT NULL,
    file_type       TEXT NOT NULL,
    content_hash    TEXT UNIQUE,
    document_type   TEXT,
    topic_tags      TEXT,           -- JSON array
    language        TEXT,
    page_count      INTEGER,
    word_count      INTEGER,
    ingested_at     DATETIME DEFAULT (datetime('now')),
    parent_source_id TEXT,
    chapter_index   INTEGER,
    summary_one_line TEXT,
    FOREIGN KEY (parent_source_id) REFERENCES sources(source_id)
);

-- Wiki 页面
CREATE TABLE IF NOT EXISTS wiki_pages (
    page_id         TEXT PRIMARY KEY,
    title           TEXT NOT NULL,
    category        TEXT NOT NULL,
    content         TEXT,
    created_at      DATETIME DEFAULT (datetime('now')),
    last_updated    DATETIME DEFAULT (datetime('now')),
    quality_score   REAL DEFAULT 0.8,
    source_count    INTEGER DEFAULT 0
);

-- 页面间交叉引用
CREATE TABLE IF NOT EXISTS page_refs (
    from_page_id    TEXT,
    to_page_id      TEXT,
    context         TEXT,
    created_at      DATETIME DEFAULT (datetime('now')),
    PRIMARY KEY (from_page_id, to_page_id),
    FOREIGN KEY (from_page_id) REFERENCES wiki_pages(page_id),
    FOREIGN KEY (to_page_id)   REFERENCES wiki_pages(page_id)
);

-- 原始文档 → Wiki 页面映射
CREATE TABLE IF NOT EXISTS source_page_map (
    source_id   TEXT,
    page_id     TEXT,
    relevance   REAL DEFAULT 1.0,
    PRIMARY KEY (source_id, page_id)
);

-- 文档分段缓存
CREATE TABLE IF NOT EXISTS segments (
    segment_id      TEXT PRIMARY KEY,
    source_id       TEXT NOT NULL,
    segment_index   INTEGER NOT NULL,
    title           TEXT,
    summary         TEXT,
    content         TEXT NOT NULL,
    token_count     INTEGER,
    parent_segment_id TEXT,
    created_at      DATETIME DEFAULT (datetime('now')),
    FOREIGN KEY (source_id) REFERENCES sources(source_id)
);

-- 向量嵌入
CREATE TABLE IF NOT EXISTS page_embeddings (
    page_id     TEXT PRIMARY KEY,
    embedding   BLOB,
    updated_at  DATETIME DEFAULT (datetime('now'))
);

-- 全文检索（jieba 预分词后写入）
CREATE VIRTUAL TABLE IF NOT EXISTS wiki_fts USING fts5(
    page_id     UNINDEXED,
    title,
    content,
    tokenize = "unicode61"
);

-- 操作日志
CREATE TABLE IF NOT EXISTS operation_log (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    op_type     TEXT,
    target_id   TEXT,
    detail      TEXT,
    tokens_in   INTEGER,
    tokens_out  INTEGER,
    cost_usd    REAL,
    created_at  DATETIME DEFAULT (datetime('now'))
);
"""


def init_db_sync() -> None:
    """同步初始化数据库（启动时调用）"""
    db_path = _get_db_path()
    conn = sqlite3.connect(str(db_path))
    conn.executescript(SCHEMA_SQL)
    conn.close()


async def get_db() -> aiosqlite.Connection:
    """获取异步数据库连接"""
    db_path = _get_db_path()
    db = await aiosqlite.connect(str(db_path))
    db.row_factory = aiosqlite.Row
    return db
