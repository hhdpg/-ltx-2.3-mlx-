"""项目与版本链服务：Prompt 组合、Segment 创建、当前版本流转。"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from app.core.config import settings
from app.core.paths import safe_join
from app.db.models import (
    GenerationProject,
    GenerationSegment,
    TaskStatus,
    TaskType,
)
from app.db.project_repositories import ProjectRepository, SegmentRepository
from app.services import file_service, video_service

logger = logging.getLogger(__name__)

MAX_SETTING_LENGTH = 2000


class ProjectError(RuntimeError):
    def __init__(self, message: str, code: str = "invalid_project") -> None:
        super().__init__(message)
        self.code = code


def project_output_dir(project_id: str) -> Path:
    """项目视频目录：output/projects/{project_id}/segments"""
    base = settings.outputs / "projects" / project_id / "segments"
    base.mkdir(parents=True, exist_ok=True)
    return base


def project_anchor_dir(project_id: str) -> Path:
    base = settings.outputs / "projects" / project_id / "anchors"
    base.mkdir(parents=True, exist_ok=True)
    return base


def segment_output_path(project_id: str, segment_id: str) -> Path:
    return safe_join(project_output_dir(project_id), f"segment_{segment_id}.mp4")


def _clean(value: str | None) -> str:
    return (value or "").strip()


# ---------- Prompt 组合 ----------
def compose_final_prompt(
    action_prompt: str,
    project: GenerationProject | None,
    append_project_prompt: bool,
) -> str:
    """把项目设定与本次动作组合成最终 CLI Prompt。

    规则（对应文档第 10 节）：
      * 源视频承担视觉上下文，不拼接任何历史 Prompt
      * 项目设定可为空；为空时不生成空区块
      * 剧情摘要不参与组合（它不是视觉条件）
    """
    action = _clean(action_prompt)
    if not action:
        raise ProjectError("本次动作提示词不能为空", "empty_prompt")

    if not append_project_prompt or project is None:
        return action

    blocks: list[str] = []
    sections = (
        ("Characters", project.character_setting),
        ("Setting", project.scene_setting),
        ("Visual style", project.style_setting),
        ("Continuity requirements", project.continuity_rules),
    )
    for label, value in sections:
        text = _clean(value)
        if text:
            blocks.append(f"{label}: {text[:MAX_SETTING_LENGTH]}")

    if not blocks:
        return action

    return "Project continuity:\n" + "\n".join(blocks) + "\n\nNext action:\n" + action


# ---------- 项目 ----------
def create_project(
    project_id: str,
    name: str,
    *,
    character_setting: str | None = None,
    scene_setting: str | None = None,
    style_setting: str | None = None,
    continuity_rules: str | None = None,
    story_summary: str | None = None,
    append_project_prompt: bool = True,
) -> GenerationProject:
    cleaned_name = _clean(name)
    if not cleaned_name:
        raise ProjectError("项目名称不能为空", "empty_name")
    return GenerationProject(
        id=project_id,
        name=cleaned_name[:200],
        character_setting=_clean(character_setting) or None,
        scene_setting=_clean(scene_setting) or None,
        style_setting=_clean(style_setting) or None,
        continuity_rules=_clean(continuity_rules) or None,
        story_summary=_clean(story_summary) or None,
        append_project_prompt=append_project_prompt,
    )


# ---------- Segment ----------
def create_segment_from_task(
    session,
    *,
    task,
    project_id: str,
    parent_segment_id: str | None,
    action_prompt: str,
    final_prompt: str | None,
    extend_frames: int | None,
    video_info: video_service.VideoInfo | None = None,
) -> GenerationSegment:
    """任务成功后创建版本记录。必须由调用方保证任务已成功且文件有效。

    Retake 的语义是"替换源版本"，因此 RETAKE 结果创建后直接设为当前版本
    （用户明确就是要那份视频被改掉）；EXTEND/初始段仍遵循保守推进规则。
    """
    project = ProjectRepository(session).get(project_id)
    if project is None:
        raise ProjectError("项目不存在", "project_missing")

    segments = SegmentRepository(session)
    segment_id = str(uuid.uuid4())
    info = video_info
    if info is None:
        info = video_service.probe_video(Path(task.output_path))

    segment = GenerationSegment(
        id=segment_id,
        project_id=project_id,
        task_id=task.id,
        parent_segment_id=parent_segment_id,
        segment_index=segments.next_index(project_id),
        video_path=str(task.output_path),
        prompt=action_prompt,
        final_prompt=final_prompt,
        extend_frames=extend_frames,
        duration_seconds=info.duration,
        width=info.width,
        height=info.height,
        frame_rate=info.frame_rate,
        task_type=task.task_type,
    )
    segments.add(segment)

    is_retake = task.task_type == "RETAKE"
    if is_retake:
        # 重拍：直接把新版本设为当前（用户意图就是替换这段视频）
        project.current_segment_id = segment.id
        ProjectRepository(session).save(project)
    # 仅当当前版本仍指向本次任务来源时才推进（不覆盖用户中途的手动切换）
    elif project.current_segment_id is None:
        project.current_segment_id = segment.id
        ProjectRepository(session).save(project)
    elif parent_segment_id and project.current_segment_id == parent_segment_id:
        project.current_segment_id = segment.id
        ProjectRepository(session).save(project)
    elif parent_segment_id is None:
        # 初始版本（无父）且已有当前版本：不自动覆盖，保留用户选择
        logger.info(
            "项目 %s 已有当前版本，初始段 %s 不自动抢占",
            project_id,
            segment.id,
        )

    task.segment_id = segment.id
    return segment


def resolve_source(segment: GenerationSegment) -> video_service.VideoInfo:
    """校验源 Segment 的视频可用且尺寸合法。"""
    path = file_service.resolve_allowed(segment.video_path, "outputs")
    if path is None:
        raise ProjectError(
            "源视频文件不存在或不在允许目录内", "source_missing"
        )
    return video_service.probe_video(path, validate_size=True)


def segment_lineage(segments: list[GenerationSegment]) -> dict[str, list[str]]:
    """返回 {segment_id: [child_id, ...]}，用于前端按父子关系渲染树。"""
    children: dict[str, list[str]] = {segment.id: [] for segment in segments}
    for segment in segments:
        parent = segment.parent_segment_id
        if parent and parent in children:
            children[parent].append(segment.id)
    return children


def delete_segment_files_guard(
    session, segment: GenerationSegment
) -> tuple[bool, str]:
    """检查 Segment 是否可安全删除（有子版本时拒绝）。"""
    children = SegmentRepository(session).children_of(segment.id)
    if children:
        return False, f"该版本仍有 {len(children)} 个子版本，无法删除"
    return True, ""


def is_video_referenced(session, video_path: str) -> bool:
    """同一视频文件是否被其他 Segment 引用。"""
    if not video_path:
        return False
    references = SegmentRepository(session).referenced_video_paths()
    return video_path in references


def cleanup_unused_video(
    session, output_path: str | None, *, keep_unreferenced: bool = False
) -> bool:
    """删除不再被任何 Segment 引用的输出视频。"""
    if not output_path:
        return False
    if keep_unreferenced:
        return False
    if is_video_referenced(session, output_path):
        logger.info("视频仍被 Segment 引用，跳过删除：%s", output_path)
        return False
    return file_service.delete_file(Path(output_path))


def anchor_path_for(project_id: str, upload: file_service.StoredUpload) -> Path:
    """把锚点图片归档到项目 anchors 目录。"""
    target = safe_join(project_anchor_dir(project_id), f"anchor_{upload.upload_id}.png")
    try:
        target.write_bytes(upload.path.read_bytes())
    except OSError as exc:
        raise ProjectError(f"保存锚点图片失败：{exc}", "anchor_save_failed") from exc
    return target


def ensure_extend_task_type() -> str:
    return TaskType.EXTEND.value


def is_terminal_status(status: str) -> bool:
    return TaskStatus(status).is_terminal
