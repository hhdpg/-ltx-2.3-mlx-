"""系统状态相关响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CheckItem(BaseModel):
    key: str
    label: str
    status: str = Field(description="ok | warn | error")
    message: str = ""
    detail: str | None = None


class HealthResponse(BaseModel):
    status: str
    app: str
    python: str
    architecture: str
    mlx_available: bool
    mlx_device: str | None = None
    mlx_error: str | None = None
    cli_available: bool
    cli_error: str | None = None
    model_configured: bool
    model_path: str | None = None
    model_error: str | None = None
    ffmpeg_available: bool
    ffmpeg_error: str | None = None
    queue_running: bool
    queue_size: int = 0
    max_queue_size: int = 0
    offline_mode: bool = True
    ready: bool = False
    blocking_reasons: list[str] = Field(default_factory=list)


class SystemInfoResponse(BaseModel):
    app: str
    app_env: str
    python_version: str
    platform: str
    architecture: str
    cpu_count: int | None = None
    total_memory_gb: float | None = None
    available_memory_gb: float | None = None
    disk_total_gb: float | None = None
    disk_free_gb: float | None = None
    model_id: str
    model_path: str | None = None
    output_dir: str
    upload_dir: str
    log_dir: str
    cli_path: str | None = None
    cli_version: str | None = None
    checks: list[CheckItem] = Field(default_factory=list)
    ready: bool = False
    blocking_reasons: list[str] = Field(default_factory=list)


class SettingsResponse(BaseModel):
    default_width: int
    default_height: int
    default_frames: int
    default_frame_rate: int
    low_ram: bool
    model_id: str
    model_path: str | None = None
    output_dir: str
    upload_dir: str
    allowed_frames: list[int]
    allowed_frame_rates: list[int]
    allowed_resolutions: list[list[int]]
    allowed_extend_frames: list[int] = Field(default_factory=list)
    default_extend_frames: int = 4
    max_prompt_length: int
    max_upload_mb: int
    max_queue_size: int
    offline_mode: bool


class SettingsUpdate(BaseModel):
    default_width: int | None = None
    default_height: int | None = None
    default_frames: int | None = None
    default_frame_rate: int | None = None
    low_ram: bool | None = None
    model_path: str | None = None
