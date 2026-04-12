"""导入质量评估 — 用本地模型对比原文与生成的 Wiki 页面"""

import json
import logging
from datetime import datetime
from pathlib import Path

from app.config import get_wiki_root
from app.llm.router import get_provider
from app.llm.prompts import EVAL_SYSTEM, EVAL_USER
from app.models.database import get_db

logger = logging.getLogger(__name__)


async def eval_ingest(
    source_id: str,
    source_text: str,
    pages_created: list[str],
) -> dict:
    """
    评估导入质量：对比原文与生成的 source_page。

    只评估 sources/ 类型的页面（严格忠于原文的要求最高）。
    使用本地模型（TASK_ROUTING["eval"] = "local"）。

    返回:
    {
        "faithfulness": int,
        "completeness": int,
        "issues": [{"type": str, "severity": str, "detail": str}],
        "summary": str,
    }
    """
    # 找到 sources/ 类型的页面
    wiki_root = get_wiki_root()
    source_pages = [p for p in pages_created if p.startswith("sources/")]

    if not source_pages:
        return {
            "faithfulness": 0,
            "completeness": 0,
            "issues": [],
            "summary": "无 source 页面，跳过评估",
        }

    # 读取第一个 source page 的内容（通常每次导入只生成一个 source page）
    page_id = source_pages[0]
    parts = page_id.split("/", 1)
    wiki_path = wiki_root / parts[0] / f"{parts[1]}.md"

    if not wiki_path.exists():
        return {
            "faithfulness": 0,
            "completeness": 0,
            "issues": [{"type": "omission", "severity": "high", "detail": "source 页面文件不存在"}],
            "summary": "source 页面文件不存在",
        }

    wiki_content = wiki_path.read_text(encoding="utf-8")

    # 截取原文前 3000 字（本地模型上下文有限）
    source_preview = source_text[:3000]
    if len(source_text) > 3000:
        source_preview += "\n\n[...原文已截断...]"

    # 截取 wiki 内容前 3000 字
    wiki_preview = wiki_content[:3000]
    if len(wiki_content) > 3000:
        wiki_preview += "\n\n[...页面已截断...]"

    # 调用本地模型做 eval
    provider = get_provider("eval")
    try:
        result = await provider.chat_json(
            messages=[
                {"role": "system", "content": EVAL_SYSTEM},
                {"role": "user", "content": EVAL_USER.format(
                    source_text=source_preview,
                    wiki_content=wiki_preview,
                )},
            ],
            max_tokens=8192,  # Qwen3.5 thinking 模式需要足够的 token 空间
        )
    except Exception as e:
        logger.warning(f"Eval 调用失败: {e}")
        return {
            "faithfulness": 0,
            "completeness": 0,
            "issues": [{"type": "omission", "severity": "low", "detail": f"eval 调用失败: {e}"}],
            "summary": "eval 调用失败",
        }

    # 规范化结果
    report = {
        "faithfulness": min(max(int(result.get("faithfulness", 0)), 0), 5),
        "completeness": min(max(int(result.get("completeness", 0)), 0), 5),
        "issues": result.get("issues", [])[:10],
        "summary": result.get("summary", ""),
    }

    # 写入数据库
    await _save_report(source_id, report)

    return report


async def _save_report(source_id: str, report: dict):
    """将 eval 结果存入数据库"""
    db = await get_db()
    try:
        await db.execute(
            """INSERT OR REPLACE INTO eval_reports
               (source_id, faithfulness, completeness, issues, summary)
               VALUES (?, ?, ?, ?, ?)""",
            (
                source_id,
                report["faithfulness"],
                report["completeness"],
                json.dumps(report["issues"], ensure_ascii=False),
                report["summary"],
            ),
        )
        await db.commit()
    finally:
        await db.close()


async def get_eval_report(source_id: str) -> dict | None:
    """从数据库读取 eval 报告"""
    db = await get_db()
    try:
        row = await db.execute(
            "SELECT * FROM eval_reports WHERE source_id = ?",
            (source_id,),
        )
        r = await row.fetchone()
        if not r:
            return None
        return {
            "source_id": r["source_id"],
            "faithfulness": r["faithfulness"],
            "completeness": r["completeness"],
            "issues": json.loads(r["issues"]) if r["issues"] else [],
            "summary": r["summary"],
            "evaluated_at": r["evaluated_at"],
        }
    finally:
        await db.close()


async def get_all_eval_stats() -> dict:
    """获取所有 eval 的汇总统计"""
    db = await get_db()
    try:
        row = await db.execute(
            """SELECT COUNT(*) as total,
                      AVG(faithfulness) as avg_faith,
                      AVG(completeness) as avg_comp,
                      MIN(faithfulness) as min_faith,
                      MIN(completeness) as min_comp
               FROM eval_reports
               WHERE faithfulness > 0"""
        )
        r = await row.fetchone()
        if not r or r["total"] == 0:
            return {"total": 0}

        # 获取问题最多的文档
        rows = await db.execute_fetchall(
            """SELECT e.source_id, s.filename, e.faithfulness, e.completeness, e.summary
               FROM eval_reports e
               JOIN sources s ON e.source_id = s.source_id
               WHERE e.faithfulness > 0
               ORDER BY (e.faithfulness + e.completeness) ASC
               LIMIT 5"""
        )

        return {
            "total": r["total"],
            "avg_faithfulness": round(r["avg_faith"], 1) if r["avg_faith"] else 0,
            "avg_completeness": round(r["avg_comp"], 1) if r["avg_comp"] else 0,
            "min_faithfulness": r["min_faith"],
            "min_completeness": r["min_comp"],
            "lowest_quality": [
                {
                    "source_id": row[0],
                    "filename": row[1],
                    "faithfulness": row[2],
                    "completeness": row[3],
                    "summary": row[4],
                }
                for row in rows
            ],
        }
    finally:
        await db.close()
