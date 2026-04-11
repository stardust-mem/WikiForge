"""Wiki 健康检查 API"""

from fastapi import APIRouter

from app.lint.checker import run_full_lint

router = APIRouter()

# 缓存最近一次 lint 报告
_last_report: dict | None = None


@router.post("/run")
async def lint_run():
    """触发 Lint 检查，返回报告"""
    global _last_report
    report = await run_full_lint()
    _last_report = report
    return report


@router.get("/report")
async def lint_report():
    """获取最近一次 Lint 报告"""
    if _last_report is None:
        return {"message": "尚未运行过检查，请先调用 POST /api/lint/run"}
    return _last_report
