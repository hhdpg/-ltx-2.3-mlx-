"""任务相关响应模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class TaskSummary(BaseModel):
    id: str
    task_type: str
    prompt: str
    prompt_excerpt: str
    width: int
    height: int
    frames: int
    frame_rate: int
    duration_seconds_est: float | None = None
    status: str
    error_message: str | None = None
    created_at: datetime
    started_at: datetime | None = None
    finished_at: datetime | None = None
    run_seconds: float | None = None
    output_ready: bool = False
    has_image: bool = False


class TaskDetail(TaskSummary):
    image_path: str | None = None
    image_url: str | None = None
    model_path: str
    mode: str
    seed: int | None = None
    output_path: str | None = None
    video_url: str | None = None
    download_url: str | None = None
    log_path: str | None = None
    exit_code: int | None = None
    pid: int | None = None
    command_preview: str | None = None


class TaskListResponse(BaseModel):
    items: list[TaskSummary]
    total: int
    limit: int
    offset: int


class TaskLogsResponse(BaseModel):
    task_id: str
    lines: list[str]
    total_lines: int
    status: str


class CreateTaskResponse(BaseModel):
    task_id: str
    status: str
    message: str


class CancelResponse(BaseModel):
    task_id: str
    status: str
    message: str


class DeleteResponse(BaseModel):
    task_id: str
    deleted_output: bool
    message: str


class UploadResponse(BaseModel):
    upload_id: str
    filename: str
    size: int
    width: int | None = None
    height: int | None = None
    content_type: str
    preview_url: str
