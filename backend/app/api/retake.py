"""局部重拍（Retake）：改写已有视频中的指定区间。

两条入口：
  * POST /api/retake            —— 针对任意成功任务（单条）
  * POST /api/projects/{id}/segments/{sid}/retake —— 针对项目的某个版本（连续）
两条路径共用同一套校验和任务创建逻辑，结果都进入全局单任务队列。
"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, Form, HTTPException, status
from sqlalchemy import func, select

from app.core.config import settings
from app.db.database import session_scope
from app.db.models import GenerationSegment, GenerationTask, TaskStatus, TaskType
from app.db.project_repositories import ProjectRepository, SegmentRepository
from app.db.repositories import TaskRepository
from app.schemas.project import RetakeResponse
from app.services import (
    file_service,
    generation_service,
    model_service,
    project_service,
    video_service,
)
from app.services.task_queue import queue_manager
from app.utils.validators import ValidationError, validate_seed

logger = logging.getLogger(__name__)

router = APIRouter(tags=["retake"])


def _parse_seed(raw: str | None) -> int | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if text in ("", "null", "random", "-1"):
        return None
    try:
        value = int(text)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="随机种子必须是整数",
        ) from None
    try:
        return validate_seed(value)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc


def _ready_or_raise() -> None:
    model = model_service.effective_model()
    if model.status == "error" or model.path is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=model.message or "模型未配置",
        )
    if not settings.cli_available:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"推理 CLI 不可用：{settings.ltx_executable or '未配置'}",
        )


def _queue_depth_or_raise() -> int:
    with session_scope() as session:
        queued = session.execute(
            select(func.count(GenerationTask.id)).where(
                GenerationTask.status == TaskStatus.QUEUED.value
            )
        ).scalar_one()
    if queued >= settings.max_queue_size:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"队列已满（最多 {settings.max_queue_size} 个等待任务）",
        )
    return int(queued)


def _duplicate_or_raise(
    *, project_id: str | None, source_segment_id: str | None
) -> None:
    """同一来源已有进行中的重拍任务时拒绝重复提交。"""
    if not project_id or not source_segment_id:
        return
    with session_scope() as session:
        count = session.execute(
            select(func.count(GenerationTask.id)).where(
                GenerationTask.status.in_(
                    (
                        TaskStatus.QUEUED.value,
                        TaskStatus.STARTING.value,
                        TaskStatus.RUNNING.value,
                    )
                ),
                GenerationTask.project_id == project_id,
                GenerationTask.source_segment_id == source_segment_id,
                GenerationTask.task_type == TaskType.RETAKE.value,
            )
        ).scalar_one()
    if count:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="该版本已有进行中的重拍任务，请等待完成",
        )


def _resolve_source_video(
    video_path: str | None,
) -> tuple[Path, video_service.VideoInfo]:
    if not video_path:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail="源视频路径缺失"
        )
    source = file_service.resolve_allowed(video_path, "outputs")
    if source is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="源视频文件不存在或不在允许目录内",
        )
    try:
        info = video_service.probe_video(source)
    except video_service.VideoError as exc:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=str(exc)
        ) from exc
    return source, info


def _clean_prompt(prompt: str) -> str:
    text = (prompt or "").strip()
    if not text:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="请描述这一段要改成什么",
        )
    if len(text) > settings.max_prompt_length:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"提示词最多 {settings.max_prompt_length} 字符",
        )
    return text


async def _create_retake(
    *,
    source_video: Path,
    source_info: video_service.VideoInfo,
    final_prompt: str,
    action_prompt: str,
    start_latent: int,
    end_latent: int,
    keep_audio: bool,
    seed: int | None,
    project_id: str | None,
    source_segment_id: str | None,
    output_file: Path | None,
    queue_depth: int,
) -> GenerationTask:
    model = model_service.effective_model()
    if model.path is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=model.message or "模型未配置"
        )
    try:
        task = generation_service.create_retake_task(
            prompt=action_prompt,
            final_prompt=final_prompt,
            source_video_path=source_video,
            retake_start=start_latent,
            retake_end=end_latent,
            keep_audio=keep_audio,
            model_path=model.path,
            source_info=source_info,
            seed=seed,
            project_id=project_id,
            source_segment_id=source_segment_id,
            output_file=output_file,
            queue_depth=queue_depth,
        )
    except generation_service.GenerationError as exc:
        code = (
            status.HTTP_429_TOO_MANY_REQUESTS
            if exc.code == "queue_full"
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=code, detail=str(exc)) from exc

    await queue_manager.submit(task.id)
    logger.info(
        "重拍任务入队 task=%s range=[%s,%s) project=%s",
        task.id,
        start_latent,
        end_latent,
        project_id or "-",
    )
    return task


# ---------- 单条路径：针对某个已完成任务 ----------
@router.post(
    "/retake",
    response_model=RetakeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retake_task(
    task_id: str = Form(...),
    prompt: str = Form(...),
    start_latent: int = Form(...),
    end_latent: int = Form(...),
    keep_audio: bool = Form(False),
    seed: str | None = Form(None),
    append_project_prompt: bool = Form(False),
) -> RetakeResponse:
    _ready_or_raise()
    queue_depth = _queue_depth_or_raise()
    action_prompt = _clean_prompt(prompt)
    parsed_seed = _parse_seed(seed)

    with session_scope() as session:
        task = TaskRepository(session).get(task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在"
            )
        if task.status != TaskStatus.SUCCEEDED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="只有已成功的任务才能重拍",
            )
        source_task_video = task.output_path
        source_task_type = task.task_type
        source_project_id = task.project_id

    _ = source_task_type  # 单条重拍不区分来源类型，任何成功视频都可

    source_video, info = _resolve_source_video(source_task_video)
    try:
        video_service.validate_retake_range(info, start_latent, end_latent)
    except video_service.VideoError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    # 单条重拍：若源任务属于项目，附带项目设定（可选开关）
    final_prompt = action_prompt
    if append_project_prompt and source_project_id:
        with session_scope() as session:
            project = ProjectRepository(session).get(source_project_id)
            if project is not None:
                try:
                    final_prompt = project_service.compose_final_prompt(
                        action_prompt, project, True
                    )
                except project_service.ProjectError:
                    final_prompt = action_prompt

    task_created = await _create_retake(
        source_video=source_video,
        source_info=info,
        final_prompt=final_prompt,
        action_prompt=action_prompt,
        start_latent=start_latent,
        end_latent=end_latent,
        keep_audio=keep_audio,
        seed=parsed_seed,
        # 单条重拍结果不自动进入项目，避免意外改变创作链
        project_id=None,
        source_segment_id=None,
        output_file=None,
        queue_depth=queue_depth,
    )

    return RetakeResponse(
        task_id=task_created.id,
        status=task_created.status,
        message="重拍任务已加入本地队列",
        final_prompt=final_prompt,
        range=_range_payload(info, start_latent, end_latent),
    )


# ---------- 连续路径：针对项目中的某个版本 ----------
@router.post(
    "/projects/{project_id}/segments/{segment_id}/retake",
    response_model=RetakeResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def retake_segment(
    project_id: str,
    segment_id: str,
    prompt: str = Form(...),
    start_latent: int = Form(...),
    end_latent: int = Form(...),
    keep_audio: bool = Form(False),
    seed: str | None = Form(None),
    append_project_prompt: bool = Form(True),
) -> RetakeResponse:
    _ready_or_raise()
    queue_depth = _queue_depth_or_raise()
    action_prompt = _clean_prompt(prompt)
    parsed_seed = _parse_seed(seed)
    _duplicate_or_raise(project_id=project_id, source_segment_id=segment_id)

    with session_scope() as session:
        project = ProjectRepository(session).get(project_id)
        if project is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在"
            )
        segment = SegmentRepository(session).get(segment_id)
        if segment is None or segment.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail="版本不存在或不属于该项目",
            )
        video_path = segment.video_path

    source_video, info = _resolve_source_video(video_path)
    try:
        video_service.validate_retake_range(info, start_latent, end_latent)
    except video_service.VideoError as exc:
        code = (
            status.HTTP_409_CONFLICT
            if exc.code == "video_unreadable"
            else status.HTTP_422_UNPROCESSABLE_ENTITY
        )
        raise HTTPException(status_code=code, detail=str(exc)) from exc

    try:
        final_prompt = project_service.compose_final_prompt(
            action_prompt, project, append_project_prompt
        )
    except project_service.ProjectError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    output_file = project_service.segment_output_path(project_id, "pending")
    _ = output_file
    # create_retake_task 会用任务 UUID 在项目目录下生成规范输出路径
    task_created = await _create_retake(
        source_video=source_video,
        source_info=info,
        final_prompt=final_prompt,
        action_prompt=action_prompt,
        start_latent=start_latent,
        end_latent=end_latent,
        keep_audio=keep_audio,
        seed=parsed_seed,
        project_id=project_id,
        source_segment_id=segment_id,
        output_file=None,
        queue_depth=queue_depth,
    )

    return RetakeResponse(
        task_id=task_created.id,
        status=task_created.status,
        message="重拍任务已加入本地队列，完成后会成为新版本",
        project_id=project_id,
        source_segment_id=segment_id,
        final_prompt=final_prompt,
        range=_range_payload(info, start_latent, end_latent),
    )


def _range_payload(
    info: video_service.VideoInfo, start_latent: int, end_latent: int
) -> dict:
    return video_service.retake_preview(info, start_latent, end_latent)


# ---------- 区间预览（前端拖动滑块时查询）----------
@router.get("/retake/source/{task_id}")
def retake_source_by_task(task_id: str) -> dict:
    """返回单条任务可用作重拍的区间信息。"""
    with session_scope() as session:
        task = TaskRepository(session).get(task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在"
            )
        if task.status != TaskStatus.SUCCEEDED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="任务未成功"
            )
        video_path = task.output_path

    _, info = _resolve_source_video(video_path)
    total_latent = video_service.frames_to_latent(info.frame_count or 0)
    return {
        "kind": "task",
        "task_id": task_id,
        "video_url": f"/api/files/{task_id}/video",
        "total_latent": total_latent,
        "source_frames": info.frame_count or 0,
        "source_duration": round(info.duration or 0, 3),
        "fps": info.frame_rate,
        "width": info.width,
        "height": info.height,
    }


@router.get("/retake/source/segment/{segment_id}")
def retake_source_by_segment(segment_id: str) -> dict:
    """返回项目版本可用作重拍的区间信息。"""
    with session_scope() as session:
        segment = SegmentRepository(session).get(segment_id)
        if segment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="版本不存在"
            )
        video_path = segment.video_path
        project_id = segment.project_id

    _, info = _resolve_source_video(video_path)
    total_latent = video_service.frames_to_latent(info.frame_count or 0)
    return {
        "kind": "segment",
        "segment_id": segment_id,
        "project_id": project_id,
        "video_url": f"/api/segments/{segment_id}/video",
        "total_latent": total_latent,
        "source_frames": info.frame_count or 0,
        "source_duration": round(info.duration or 0, 3),
        "fps": info.frame_rate,
        "width": info.width,
        "height": info.height,
    }
