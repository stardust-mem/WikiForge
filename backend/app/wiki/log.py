"""log.md — 操作日志追加"""
from datetime import datetime
from pathlib import Path
from app.config import get_wiki_root


def append_log(op_type: str, detail: str) -> None:
    """追加一条日志到 wiki-root/log.md

    格式: ## [YYYY-MM-DD HH:MM] op_type | detail
    """
    wiki_root = get_wiki_root()
    log_path = wiki_root / "log.md"
    now = datetime.now().strftime("%Y-%m-%d %H:%M")
    entry = f"## [{now}] {op_type} | {detail}\n\n"

    if not log_path.exists():
        header = "# 操作日志\n\n> 自动维护，记录每次 Ingest / Query / Lint 操作\n\n"
        log_path.write_text(header + entry, encoding="utf-8")
    else:
        with open(log_path, "a", encoding="utf-8") as f:
            f.write(entry)
