"""Ingest 任务管理 — 异步任务追踪与状态更新"""

import asyncio
import traceback
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


class TaskStatus(str, Enum):
    PENDING = "pending"
    EXTRACTING = "extracting"       # 提取文本
    CLASSIFYING = "classifying"     # 自动分类
    SEGMENTING = "segmenting"       # 智能分段
    GENERATING = "generating"       # 生成 Wiki
    INDEXING = "indexing"            # 构建索引
    SAVING = "saving"               # 写入数据库
    COMPLETED = "completed"
    FAILED = "failed"


STEP_LABELS = {
    TaskStatus.PENDING: "等待处理",
    TaskStatus.EXTRACTING: "正在提取文档内容...",
    TaskStatus.CLASSIFYING: "正在自动分类...",
    TaskStatus.SEGMENTING: "正在智能分段...",
    TaskStatus.GENERATING: "正在生成 Wiki 页面...",
    TaskStatus.INDEXING: "正在构建搜索索引...",
    TaskStatus.SAVING: "正在保存数据...",
    TaskStatus.COMPLETED: "处理完成",
    TaskStatus.FAILED: "处理失败",
}


@dataclass
class IngestTask:
    task_id: str
    filename: str
    status: TaskStatus = TaskStatus.PENDING
    progress_label: str = "等待处理"
    error: Optional[str] = None
    result: Optional[dict] = None
    created_at: str = field(default_factory=lambda: datetime.now().isoformat())


# 全局任务存储（内存中，进程重启后丢失，足够用）
_tasks: dict[str, IngestTask] = {}


def create_task(task_id: str, filename: str) -> IngestTask:
    task = IngestTask(task_id=task_id, filename=filename)
    _tasks[task_id] = task
    return task


def update_task_status(task_id: str, status: TaskStatus) -> None:
    if task_id in _tasks:
        _tasks[task_id].status = status
        _tasks[task_id].progress_label = STEP_LABELS[status]


def fail_task(task_id: str, error: str) -> None:
    if task_id in _tasks:
        _tasks[task_id].status = TaskStatus.FAILED
        _tasks[task_id].progress_label = "处理失败"
        _tasks[task_id].error = error


def complete_task(task_id: str, result: dict) -> None:
    if task_id in _tasks:
        _tasks[task_id].status = TaskStatus.COMPLETED
        _tasks[task_id].progress_label = "处理完成"
        _tasks[task_id].result = result


def get_task(task_id: str) -> Optional[IngestTask]:
    return _tasks.get(task_id)


def get_all_tasks() -> list[IngestTask]:
    return sorted(_tasks.values(), key=lambda t: t.created_at, reverse=True)
