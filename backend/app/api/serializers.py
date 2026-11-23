"""任务序列化：ORM 对象 → 响应模型。"""

from __future__ import annotations

from pathlib import Path

from app.db.models import GenerationTask, TaskStatus
from app.schemas.task import TaskDetail, TaskSummary
from app.utils.validators import display_duration


def _excerpt(prompt: str, limit: int = 80) -> str:
    cleaned = " ".join((prompt or "").split())
    return cleaned if len(cleaned) <= limit else cleaned[: limit - 1] + "…"


def _iso(value):
    return value


def run_seconds(task: GenerationTask) -> float | None:
    if task.duration_seconds is not None:
        return task.duration_seconds
    return None


def to_summary(task: GenerationTask) -> TaskSummary:
    return TaskSummary(
        id=task.id,
        task_type=task.task_type,
        prompt=task.prompt,
        prompt_excerpt=_excerpt(task.prompt),
        width=task.width,
        height=task.height,
        frames=task.frames,
        frame_rate=task.frame_rate,
        duration_seconds_est=display_duration(task.frames, task.frame_rate),
        status=task.status,
        error_message=task.error_message if task.status == TaskStatus.FAILED.value else None,
        created_at=task.created_at,
        started_at=task.started_at,
        finished_at=task.finished_at,
        run_seconds=run_seconds(task),
        output_ready=bool(
            task.status == TaskStatus.SUCCEEDED.value
            and task.output_path
            and Path(task.output_path).is_file()
        ),
        has_image=bool(task.image_path),
    )


def to_detail(task: GenerationTask, command_preview: str | None = None) -> TaskDetail:
    base = to_summary(task)
    ready = base.output_ready
    return TaskDetail(
        **base.model_dump(),
        image_path=task.image_path,
        image_url=f"/api/files/uploads/{Path(task.image_path).name}"
        if task.image_path
        else None,
        model_path=task.model_path,
        mode=task.mode,
        seed=task.seed,
        output_path=task.output_path,
        video_url=f"/api/files/{task.id}/video" if ready else None,
        download_url=f"/api/files/{task.id}/download" if ready else None,
        log_path=task.log_path,
        exit_code=task.exit_code,
        pid=task.pid,
        command_preview=command_preview,
    )
