"""项目与续写相关响应/请求模型。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class ProjectCreate(BaseModel):
    name: str = Field(min_length=1, max_length=200)
    character_setting: str | None = None
    scene_setting: str | None = None
    style_setting: str | None = None
    continuity_rules: str | None = None
    story_summary: str | None = None
    append_project_prompt: bool = True


class ProjectUpdate(BaseModel):
    name: str | None = Field(default=None, max_length=200)
    character_setting: str | None = None
    scene_setting: str | None = None
    style_setting: str | None = None
    continuity_rules: str | None = None
    story_summary: str | None = None
    append_project_prompt: bool | None = None


class SegmentSummary(BaseModel):
    id: str
    project_id: str
    task_id: str
    parent_segment_id: str | None
    segment_index: int
    video_url: str
    prompt: str
    final_prompt: str | None
    extend_frames: int | None
    duration_seconds: float | None
    width: int | None
    height: int | None
    frame_rate: float | None
    task_type: str
    created_at: datetime
    is_current: bool
    child_count: int = 0
    video_ready: bool = False


class ProjectSummary(BaseModel):
    id: str
    name: str
    current_segment_id: str | None
    segment_count: int
    append_project_prompt: bool
    created_at: datetime
    updated_at: datetime
    current_video_url: str | None = None
    current_duration_seconds: float | None = None


class ProjectDetail(ProjectSummary):
    character_setting: str | None
    scene_setting: str | None
    style_setting: str | None
    continuity_rules: str | None
    story_summary: str | None


class ProjectListResponse(BaseModel):
    items: list[ProjectSummary]
    total: int


class SegmentListResponse(BaseModel):
    project_id: str
    current_segment_id: str | None
    items: list[SegmentSummary]
    children: dict[str, list[str]]


class AttachSegmentRequest(BaseModel):
    task_id: str


class ExtendRequest(BaseModel):
    source_segment_id: str
    prompt: str = Field(min_length=1)
    extend_frames: int = Field(ge=1, le=32)
    seed: int | None = None
    append_project_prompt: bool = True
    # 先提交最终 Prompt 预览时可不传，后端会按规则组合
    final_prompt: str | None = None
    anchor_frame: int | None = None
    anchor_strength: float | None = None


class ExtendResponse(BaseModel):
    task_id: str
    project_id: str
    source_segment_id: str
    status: str
    message: str
    final_prompt: str | None = None
    estimated_added_seconds: float | None = None
    estimated_added_frames: int | None = None


class SetCurrentSegmentRequest(BaseModel):
    segment_id: str


class PromptPreviewRequest(BaseModel):
    prompt: str
    append_project_prompt: bool = True


class PromptPreviewResponse(BaseModel):
    final_prompt: str


class DeleteProjectResponse(BaseModel):
    project_id: str
    deleted_segments: int
    deleted_files: int
    message: str


# ---------- 局部重拍（Retake）----------
class RetakeRangeInfo(BaseModel):
    start_latent: int
    end_latent: int
    total_latent: int
    start_frame: int
    end_frame: int
    start_seconds: float
    end_seconds: float
    duration_seconds: float
    source_frames: int
    source_duration: float
    fps: float


class RetakeResponse(BaseModel):
    task_id: str
    status: str
    message: str
    project_id: str | None = None
    source_segment_id: str | None = None
    final_prompt: str | None = None
    range: RetakeRangeInfo | None = None
