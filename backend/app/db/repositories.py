"""数据访问层：任务与设置的持久化操作。"""

from __future__ import annotations

from collections.abc import Sequence
from datetime import datetime, timezone

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.db.models import AppSetting, GenerationTask, TaskStatus, utcnow

ACTIVE_STATUSES = (
    TaskStatus.QUEUED.value,
    TaskStatus.STARTING.value,
    TaskStatus.RUNNING.value,
    TaskStatus.CANCELING.value,
)


class TaskRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    # ---- 写入 ----
    def add(self, task: GenerationTask) -> GenerationTask:
        self.session.add(task)
        self.session.flush()
        return task

    def save(self, task: GenerationTask) -> GenerationTask:
        self.session.add(task)
        self.session.flush()
        return task

    def get(self, task_id: str) -> GenerationTask | None:
        return self.session.get(GenerationTask, task_id)

    def delete(self, task: GenerationTask) -> None:
        self.session.delete(task)

    # ---- 查询 ----
    def list_tasks(
        self,
        *,
        status: str | None = None,
        task_type: str | None = None,
        limit: int = 20,
        offset: int = 0,
    ) -> tuple[list[GenerationTask], int]:
        stmt = select(GenerationTask)
        count_stmt = select(func.count(GenerationTask.id))
        if status:
            stmt = stmt.where(GenerationTask.status == status)
            count_stmt = count_stmt.where(GenerationTask.status == status)
        if task_type:
            stmt = stmt.where(GenerationTask.task_type == task_type)
            count_stmt = count_stmt.where(GenerationTask.task_type == task_type)

        total = self.session.execute(count_stmt).scalar_one()
        stmt = stmt.order_by(GenerationTask.created_at.desc()).limit(limit).offset(offset)
        items = list(self.session.execute(stmt).scalars().all())
        return items, int(total)

    def recent(self, limit: int = 5) -> list[GenerationTask]:
        stmt = (
            select(GenerationTask)
            .order_by(GenerationTask.created_at.desc())
            .limit(limit)
        )
        return list(self.session.execute(stmt).scalars().all())

    def active_tasks(self) -> list[GenerationTask]:
        stmt = select(GenerationTask).where(GenerationTask.status.in_(ACTIVE_STATUSES))
        return list(self.session.execute(stmt).scalars().all())

    def queued_tasks_ordered(self) -> list[GenerationTask]:
        stmt = (
            select(GenerationTask)
            .where(GenerationTask.status == TaskStatus.QUEUED.value)
            .order_by(GenerationTask.created_at.asc())
        )
        return list(self.session.execute(stmt).scalars().all())

    def count_active(self) -> int:
        stmt = select(func.count(GenerationTask.id)).where(
            GenerationTask.status.in_(ACTIVE_STATUSES)
        )
        return int(self.session.execute(stmt).scalar_one())

    def count_queued(self) -> int:
        stmt = select(func.count(GenerationTask.id)).where(
            GenerationTask.status == TaskStatus.QUEUED.value
        )
        return int(self.session.execute(stmt).scalar_one())

    # ---- 状态流转 ----
    def mark_started(self, task: GenerationTask, pid: int | None = None) -> None:
        task.set_status(TaskStatus.STARTING)
        task.started_at = utcnow()
        task.pid = pid
        self.save(task)

    def mark_running(self, task: GenerationTask) -> None:
        if task.status == TaskStatus.RUNNING.value:
            return
        task.set_status(TaskStatus.RUNNING)
        self.save(task)

    def mark_succeeded(self, task: GenerationTask, output_path: str) -> None:
        now = utcnow()
        task.set_status(TaskStatus.SUCCEEDED)
        task.output_path = output_path
        task.finished_at = now
        task.duration_seconds = _duration(task, now)
        task.error_message = None
        self.save(task)

    def mark_failed(
        self, task: GenerationTask, message: str, exit_code: int | None = None
    ) -> None:
        now = utcnow()
        task.set_status(TaskStatus.FAILED)
        task.error_message = message[:4000]
        task.exit_code = exit_code
        task.finished_at = now
        task.duration_seconds = _duration(task, now)
        self.save(task)

    def mark_cancel_requested(self, task: GenerationTask) -> None:
        task.set_status(TaskStatus.CANCELING)
        self.save(task)

    def mark_canceled(self, task: GenerationTask) -> None:
        now = utcnow()
        task.set_status(TaskStatus.CANCELED)
        task.finished_at = now
        task.duration_seconds = _duration(task, now)
        self.save(task)

    # ---- 启动恢复 ----
    def fail_interrupted(self) -> list[GenerationTask]:
        """把 STARTING/RUNNING/CANCELING 的残留任务标记失败。"""
        stmt = select(GenerationTask).where(
            GenerationTask.status.in_(
                (
                    TaskStatus.STARTING.value,
                    TaskStatus.RUNNING.value,
                    TaskStatus.CANCELING.value,
                )
            )
        )
        tasks = list(self.session.execute(stmt).scalars().all())
        for task in tasks:
            self.mark_failed(task, "服务异常退出，任务未能恢复")
        return tasks


def _duration(task: GenerationTask, end: datetime) -> float:
    start = task.started_at or task.created_at
    if start is None:
        return 0.0
    if start.tzinfo is None:
        start = start.replace(tzinfo=timezone.utc)
    if end.tzinfo is None:
        end = end.replace(tzinfo=timezone.utc)
    return round(max((end - start).total_seconds(), 0.0), 2)


class SettingRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def get_all(self) -> dict[str, str]:
        rows: Sequence[AppSetting] = (
            self.session.execute(select(AppSetting)).scalars().all()
        )
        return {row.key: row.value for row in rows}

    def get(self, key: str, default: str | None = None) -> str | None:
        row = self.session.get(AppSetting, key)
        return row.value if row else default

    def set(self, key: str, value: str) -> None:
        row = self.session.get(AppSetting, key)
        if row is None:
            self.session.add(AppSetting(key=key, value=value))
        else:
            row.value = value
            row.updated_at = utcnow()
        self.session.flush()

    def delete(self, key: str) -> None:
        row = self.session.get(AppSetting, key)
        if row is not None:
            self.session.delete(row)
            self.session.flush()
