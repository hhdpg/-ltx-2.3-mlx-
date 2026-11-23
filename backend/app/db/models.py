"""ORM 模型：任务表与设置表。"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import Enum

from sqlalchemy import (
    Boolean,
    DateTime,
    Float,
    Integer,
    String,
    Text,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.database import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc)


class TaskStatus(str, Enum):
    QUEUED = "QUEUED"
    STARTING = "STARTING"
    RUNNING = "RUNNING"
    SUCCEEDED = "SUCCEEDED"
    FAILED = "FAILED"
    CANCELING = "CANCELING"
    CANCELED = "CANCELED"

    @property
    def is_terminal(self) -> bool:
        return self in (TaskStatus.SUCCEEDED, TaskStatus.FAILED, TaskStatus.CANCELED)

    @property
    def is_active(self) -> bool:
        return self in (
            TaskStatus.QUEUED,
            TaskStatus.STARTING,
            TaskStatus.RUNNING,
            TaskStatus.CANCELING,
        )


class TaskType(str, Enum):
    T2V = "T2V"
    I2V = "I2V"
    EXTEND = "EXTEND"
    RETAKE = "RETAKE"


class GenerationTask(Base):
    __tablename__ = "generation_task"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    task_type: Mapped[str] = mapped_column(String(10), nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    model_path: Mapped[str] = mapped_column(Text, nullable=False)
    mode: Mapped[str] = mapped_column(String(20), nullable=False, default="distilled")
    width: Mapped[int] = mapped_column(Integer, nullable=False)
    height: Mapped[int] = mapped_column(Integer, nullable=False)
    frames: Mapped[int] = mapped_column(Integer, nullable=False)
    frame_rate: Mapped[int] = mapped_column(Integer, nullable=False)
    seed: Mapped[int | None] = mapped_column(Integer, nullable=True)
    status: Mapped[str] = mapped_column(
        String(20), nullable=False, default=TaskStatus.QUEUED.value, index=True
    )
    output_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    log_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    exit_code: Mapped[int | None] = mapped_column(Integer, nullable=True)
    pid: Mapped[int | None] = mapped_column(Integer, nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    finished_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)

    # ---- V1.1 连续续写字段（全部可空，向后兼容）----
    project_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    source_segment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    extend_frames: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source_video_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    final_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    anchor_image_path: Mapped[str | None] = mapped_column(Text, nullable=True)
    anchor_frame: Mapped[int | None] = mapped_column(Integer, nullable=True)
    anchor_strength: Mapped[float | None] = mapped_column(Float, nullable=True)
    segment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)

    # ---- V1.2 局部重拍（retake）：latent 帧区间，左闭右开 ----
    retake_start: Mapped[int | None] = mapped_column(Integer, nullable=True)
    retake_end: Mapped[int | None] = mapped_column(Integer, nullable=True)
    keep_audio: Mapped[bool | None] = mapped_column(Boolean, nullable=True)

    # ---- 便捷属性 ----
    @property
    def status_enum(self) -> TaskStatus:
        return TaskStatus(self.status)

    @property
    def is_extend(self) -> bool:
        return self.task_type == TaskType.EXTEND.value

    @property
    def is_retake(self) -> bool:
        return self.task_type == TaskType.RETAKE.value

    def set_status(self, status: TaskStatus) -> None:
        self.status = status.value


class GenerationProject(Base):
    """一条创作主题：包含若干视频版本（Segment）。"""

    __tablename__ = "generation_project"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    name: Mapped[str] = mapped_column(String(200), nullable=False)
    character_setting: Mapped[str | None] = mapped_column(Text, nullable=True)
    scene_setting: Mapped[str | None] = mapped_column(Text, nullable=True)
    style_setting: Mapped[str | None] = mapped_column(Text, nullable=True)
    continuity_rules: Mapped[str | None] = mapped_column(Text, nullable=True)
    story_summary: Mapped[str | None] = mapped_column(Text, nullable=True)
    append_project_prompt: Mapped[bool] = mapped_column(
        "append_project_prompt", default=True, nullable=False
    )
    current_segment_id: Mapped[str | None] = mapped_column(String(36), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )


class GenerationSegment(Base):
    """一次成功生成产生的视频版本，构成版本链。"""

    __tablename__ = "generation_segment"

    id: Mapped[str] = mapped_column(String(36), primary_key=True)
    project_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    task_id: Mapped[str] = mapped_column(String(36), nullable=False, index=True)
    parent_segment_id: Mapped[str | None] = mapped_column(
        String(36), nullable=True, index=True
    )
    segment_index: Mapped[int] = mapped_column(Integer, nullable=False, default=1)
    video_path: Mapped[str] = mapped_column(Text, nullable=False)
    prompt: Mapped[str] = mapped_column(Text, nullable=False)
    final_prompt: Mapped[str | None] = mapped_column(Text, nullable=True)
    extend_frames: Mapped[int | None] = mapped_column(Integer, nullable=True)
    duration_seconds: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    frame_rate: Mapped[float | None] = mapped_column(Float, nullable=True)
    task_type: Mapped[str] = mapped_column(String(10), nullable=False, default="T2V")
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, index=True
    )


class AppSetting(Base):
    __tablename__ = "app_setting"

    key: Mapped[str] = mapped_column(String(64), primary_key=True)
    value: Mapped[str] = mapped_column(Text, nullable=False)
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, default=utcnow, onupdate=utcnow
    )
