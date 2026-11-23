"""项目、版本链与 Extend 任务接口。"""

from __future__ import annotations

import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, File, Form, HTTPException, Query, UploadFile, status
from sqlalchemy import func, select

from app.core.config import settings
from app.db.database import session_scope
from app.db.models import GenerationSegment, GenerationTask, TaskStatus, TaskType
from app.db.project_repositories import ProjectRepository, SegmentRepository
from app.db.repositories import TaskRepository
from app.schemas.project import (
    AttachSegmentRequest,
    DeleteProjectResponse,
    ExtendRequest,
    ExtendResponse,
    ProjectCreate,
    ProjectDetail,
    ProjectListResponse,
    ProjectSummary,
    ProjectUpdate,
    PromptPreviewRequest,
    PromptPreviewResponse,
    SegmentListResponse,
    SegmentSummary,
    SetCurrentSegmentRequest,
)
from app.services import (
    file_service,
    generation_service,
    model_service,
    project_service,
    video_service,
)
from app.services.task_queue import queue_manager
from app.utils.validators import ValidationError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["projects"])


# ---------- 序列化 ----------
def _video_url(segment: GenerationSegment) -> str:
    return f"/api/segments/{segment.id}/video"


def _video_ready(path: str | None) -> bool:
    return file_service.output_ready(path)[0]


def _to_segment_summary(
    segment: GenerationSegment, current_id: str | None, child_count: int = 0
) -> SegmentSummary:
    return SegmentSummary(
        id=segment.id,
        project_id=segment.project_id,
        task_id=segment.task_id,
        parent_segment_id=segment.parent_segment_id,
        segment_index=segment.segment_index,
        video_url=_video_url(segment),
        prompt=segment.prompt,
        final_prompt=segment.final_prompt,
        extend_frames=segment.extend_frames,
        duration_seconds=segment.duration_seconds,
        width=segment.width,
        height=segment.height,
        frame_rate=segment.frame_rate,
        task_type=segment.task_type,
        created_at=segment.created_at,
        is_current=segment.id == current_id,
        child_count=child_count,
        video_ready=_video_ready(segment.video_path),
    )


def _to_project_summary(
    project, segment_count: int, current_segment: GenerationSegment | None
) -> ProjectSummary:
    return ProjectSummary(
        id=project.id,
        name=project.name,
        current_segment_id=project.current_segment_id,
        segment_count=segment_count,
        append_project_prompt=bool(project.append_project_prompt),
        created_at=project.created_at,
        updated_at=project.updated_at,
        current_video_url=_video_url(current_segment) if current_segment else None,
        current_duration_seconds=(
            current_segment.duration_seconds if current_segment else None
        ),
    )


def _load_project(session, project_id: str):
    project = ProjectRepository(session).get(project_id)
    if project is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在")
    return project


def _parse_optional_int(raw: str | None) -> int | None:
    if raw is None:
        return None
    text = str(raw).strip()
    if text in ("", "null", "random", "-1"):
        return None
    try:
        return int(text)
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="随机种子必须是整数",
        ) from None


# ---------- 项目 CRUD ----------
@router.post(
    "/projects", response_model=ProjectDetail, status_code=status.HTTP_201_CREATED
)
def create_project(payload: ProjectCreate) -> ProjectDetail:
    with session_scope() as session:
        project = project_service.create_project(
            str(uuid.uuid4()),
            payload.name,
            character_setting=payload.character_setting,
            scene_setting=payload.scene_setting,
            style_setting=payload.style_setting,
            continuity_rules=payload.continuity_rules,
            story_summary=payload.story_summary,
            append_project_prompt=payload.append_project_prompt,
        )
        ProjectRepository(session).add(project)
        detail = _project_detail(session, project)
    return detail


@router.get("/projects", response_model=ProjectListResponse)
def list_projects() -> ProjectListResponse:
    items: list[ProjectSummary] = []
    with session_scope() as session:
        projects = ProjectRepository(session).list_all()
        projects_repo = ProjectRepository(session)
        seg_repo = SegmentRepository(session)
        for project in projects:
            count = seg_repo.count_by_project(project.id)
            current = (
                seg_repo.get(project.current_segment_id)
                if project.current_segment_id
                else None
            )
            items.append(_to_project_summary(project, count, current))
        total = len(items)
        del projects_repo
    return ProjectListResponse(items=items, total=total)


@router.get("/projects/{project_id}", response_model=ProjectDetail)
def get_project(project_id: str) -> ProjectDetail:
    with session_scope() as session:
        project = _load_project(session, project_id)
        return _project_detail(session, project)


def _project_detail(session, project) -> ProjectDetail:
    seg_repo = SegmentRepository(session)
    count = seg_repo.count_by_project(project.id)
    current = (
        seg_repo.get(project.current_segment_id) if project.current_segment_id else None
    )
    summary = _to_project_summary(project, count, current)
    return ProjectDetail(
        **summary.model_dump(),
        character_setting=project.character_setting,
        scene_setting=project.scene_setting,
        style_setting=project.style_setting,
        continuity_rules=project.continuity_rules,
        story_summary=project.story_summary,
    )


@router.put("/projects/{project_id}", response_model=ProjectDetail)
def update_project(project_id: str, payload: ProjectUpdate) -> ProjectDetail:
    with session_scope() as session:
        repo = ProjectRepository(session)
        project = _load_project(session, project_id)

        if payload.name is not None:
            name = payload.name.strip()
            if not name:
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail="项目名称不能为空",
                )
            project.name = name[:200]
        for field in (
            "character_setting",
            "scene_setting",
            "style_setting",
            "continuity_rules",
            "story_summary",
        ):
            value = getattr(payload, field)
            if value is not None:
                setattr(project, field, value.strip() or None)
        if payload.append_project_prompt is not None:
            project.append_project_prompt = payload.append_project_prompt

        repo.save(project)
        return _project_detail(session, project)


@router.delete("/projects/{project_id}", response_model=DeleteProjectResponse)
def delete_project(
    project_id: str,
    delete_videos: bool = Query(False),
) -> DeleteProjectResponse:
    with session_scope() as session:
        repo = ProjectRepository(session)
        project = _load_project(session, project_id)
        seg_repo = SegmentRepository(session)
        segments = seg_repo.list_by_project(project_id)

        # 有任务仍在进行时拒绝删除
        running = session.execute(
            select(func.count(GenerationTask.id)).where(
                GenerationTask.project_id == project_id,
                GenerationTask.status.in_(
                    (
                        TaskStatus.QUEUED.value,
                        TaskStatus.STARTING.value,
                        TaskStatus.RUNNING.value,
                        TaskStatus.CANCELING.value,
                    )
                ),
            )
        ).scalar_one()
        if running:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="项目仍有进行中的任务，请先等待完成或取消",
            )

        deleted_files = 0
        if delete_videos:
            shared = _other_projects_referenced_paths(session, project_id)
            for segment in segments:
                if segment.video_path in shared:
                    logger.info("视频被其他项目引用，保留：%s", segment.video_path)
                    continue
                path = file_service.resolve_allowed(segment.video_path, "outputs")
                if path and file_service.delete_file(path):
                    deleted_files += 1

        for segment in segments:
            seg_repo.delete(segment)
        repo.delete(project)

    return DeleteProjectResponse(
        project_id=project_id,
        deleted_segments=len(segments),
        deleted_files=deleted_files,
        message="项目已删除" + ("（含视频文件）" if delete_videos else "（保留视频文件）"),
    )


def _other_projects_referenced_paths(session, project_id: str) -> set[str]:
    stmt = select(GenerationSegment.video_path).where(
        GenerationSegment.project_id != project_id
    )
    return {row for row in session.execute(stmt).scalars().all() if row}


# ---------- Segment ----------
@router.get("/projects/{project_id}/segments", response_model=SegmentListResponse)
def list_segments(project_id: str) -> SegmentListResponse:
    with session_scope() as session:
        project = _load_project(session, project_id)
        seg_repo = SegmentRepository(session)
        segments = seg_repo.list_by_project(project_id)
        children = project_service.segment_lineage(segments)
        items = [
            _to_segment_summary(
                segment, project.current_segment_id, len(children.get(segment.id, []))
            )
            for segment in segments
        ]
        return SegmentListResponse(
            project_id=project_id,
            current_segment_id=project.current_segment_id,
            items=items,
            children=children,
        )


@router.post(
    "/projects/{project_id}/segments",
    response_model=SegmentSummary,
    status_code=status.HTTP_201_CREATED,
)
def attach_segment(project_id: str, payload: AttachSegmentRequest) -> SegmentSummary:
    """把已存在的成功视频加入项目，作为初始版本。"""
    with session_scope() as session:
        project = _load_project(session, project_id)
        task = TaskRepository(session).get(payload.task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在"
            )
        if task.status != TaskStatus.SUCCEEDED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="只有成功的任务才能加入项目"
            )
        if task.task_type in (TaskType.EXTEND.value, TaskType.RETAKE.value):
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="续写/重拍任务本身已属于某个项目",
            )
        ready, problem = file_service.output_ready(task.output_path)
        if not ready:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=problem or "输出视频不可用",
            )

        seg_repo = SegmentRepository(session)
        if seg_repo.get_by_task(task.id):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="该任务已加入项目"
            )

        try:
            info = video_service.probe_video(Path(task.output_path))
        except video_service.VideoError as exc:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=str(exc)
            ) from exc

        segment = project_service.create_segment_from_task(
            session,
            task=task,
            project_id=project.id,
            parent_segment_id=None,
            action_prompt=task.prompt,
            final_prompt=task.final_prompt or task.prompt,
            extend_frames=None,
            video_info=info,
        )
        task.project_id = project.id
        TaskRepository(session).save(task)
        session.flush()
        return _to_segment_summary(segment, project.current_segment_id)


@router.put(
    "/projects/{project_id}/current-segment", response_model=SegmentSummary
)
def set_current_segment(
    project_id: str, payload: SetCurrentSegmentRequest
) -> SegmentSummary:
    with session_scope() as session:
        repo = ProjectRepository(session)
        project = _load_project(session, project_id)
        seg_repo = SegmentRepository(session)
        segment = seg_repo.get(payload.segment_id)
        if segment is None or segment.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="版本不属于该项目"
            )
        if not _video_ready(segment.video_path):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="该版本的视频文件不可用"
            )
        project.current_segment_id = segment.id
        repo.save(project)
        return _to_segment_summary(
            segment, project.current_segment_id, len(seg_repo.children_of(segment.id))
        )


@router.delete("/segments/{segment_id}")
def delete_segment(segment_id: str, delete_video: bool = Query(False)) -> dict:
    with session_scope() as session:
        seg_repo = SegmentRepository(session)
        segment = seg_repo.get(segment_id)
        if segment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="版本不存在"
            )
        ok, message = project_service.delete_segment_files_guard(session, segment)
        if not ok:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail=message
            )

        project = ProjectRepository(session).get(segment.project_id)
        remaining = [
            item for item in seg_repo.list_by_project(segment.project_id)
            if item.id != segment.id
        ]
        if project and project.current_segment_id == segment.id:
            project.current_segment_id = (
                remaining[-1].id if remaining else None
            )
            ProjectRepository(session).save(project)

        deleted_file = False
        if delete_video and not project_service.is_video_referenced(
            session, segment.video_path
        ):
            path = file_service.resolve_allowed(segment.video_path, "outputs")
            if path:
                deleted_file = file_service.delete_file(path)

        seg_repo.delete(segment)

    return {
        "segment_id": segment_id,
        "deleted_video": deleted_file,
        "message": "版本已删除",
    }


# ---------- Prompt 预览 ----------
@router.post(
    "/projects/{project_id}/prompt-preview", response_model=PromptPreviewResponse
)
def preview_prompt(project_id: str, payload: PromptPreviewRequest) -> PromptPreviewResponse:
    with session_scope() as session:
        project = _load_project(session, project_id)
        try:
            final = project_service.compose_final_prompt(
                payload.prompt, project, payload.append_project_prompt
            )
        except project_service.ProjectError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        return PromptPreviewResponse(final_prompt=final)


# ---------- Extend ----------
@router.post(
    "/projects/{project_id}/extend",
    response_model=ExtendResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_extend(
    project_id: str,
    source_segment_id: str = Form(...),
    prompt: str = Form(...),
    extend_frames: int = Form(...),
    seed: str | None = Form(None),
    append_project_prompt: bool = Form(True),
    anchor_frame: int | None = Form(None),
    anchor_strength: float | None = Form(None),
    anchor_image: UploadFile | None = File(None),
) -> ExtendResponse:
    payload = ExtendRequest(
        source_segment_id=source_segment_id,
        prompt=prompt,
        extend_frames=extend_frames,
        seed=_parse_optional_int(seed),
        append_project_prompt=append_project_prompt,
        anchor_frame=anchor_frame,
        anchor_strength=anchor_strength,
    )
    # 1) 环境前置检查
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

    # 2) 参数白名单
    try:
        video_service.validate_extend_frames(payload.extend_frames)
    except video_service.VideoError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc
    try:
        seed = payload.seed
        if seed is not None:
            from app.utils.validators import validate_seed

            seed = validate_seed(seed)
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    action_prompt = (payload.prompt or "").strip()
    if not action_prompt:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="本次动作提示词不能为空"
        )
    if len(action_prompt) > settings.max_prompt_length:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"提示词最多 {settings.max_prompt_length} 字符",
        )

    if payload.anchor_strength is not None and not (
        0.0 <= payload.anchor_strength <= 1.0
    ):
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="锚点强度必须在 0 ~ 1 之间",
        )

    # 3) 队列容量
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

    # 4) 源版本校验
    with session_scope() as session:
        project = _load_project(session, project_id)
        seg_repo = SegmentRepository(session)
        source = seg_repo.get(payload.source_segment_id)
        if source is None or source.project_id != project_id:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="源版本不存在或不属于该项目"
            )
        source_video = file_service.resolve_allowed(source.video_path, "outputs")
        if source_video is None:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="源视频文件不存在或不可访问"
            )
        source_task = TaskRepository(session).get(source.task_id)
        if source_task is None or source_task.status != TaskStatus.SUCCEEDED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="源版本对应的任务未成功"
            )

        # 同源重复提交保护：已有排队/运行中的续写任务则拒绝
        duplicate = session.execute(
            select(func.count(GenerationTask.id)).where(
                GenerationTask.status.in_(
                    (
                        TaskStatus.QUEUED.value,
                        TaskStatus.STARTING.value,
                        TaskStatus.RUNNING.value,
                    )
                ),
                GenerationTask.project_id == project_id,
                GenerationTask.source_segment_id == payload.source_segment_id,
            )
        ).scalar_one()
        if duplicate:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="该版本已有进行中的续写任务，请等待完成",
            )

        try:
            source_info = video_service.probe_video(source_video, validate_size=True)
        except video_service.VideoError as exc:
            code = (
                status.HTTP_422_UNPROCESSABLE_ENTITY
                if exc.code == "video_size_invalid"
                else status.HTTP_409_CONFLICT
            )
            raise HTTPException(status_code=code, detail=str(exc)) from exc

        try:
            final_prompt = project_service.compose_final_prompt(
                action_prompt, project, payload.append_project_prompt
            )
        except project_service.ProjectError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc

        # 5) 可选锚点图片（存档到项目目录，不使用用户原始文件名）
        anchor_path: Path | None = None
        if anchor_image is not None:
            data = await anchor_image.read()
            try:
                stored = file_service.save_upload(data, anchor_image.filename or "anchor")
            except file_service.UploadError as exc:
                code = {
                    "file_too_large": status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                    "unsupported_type": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
                }.get(exc.error_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
                raise HTTPException(status_code=code, detail=str(exc)) from exc
            anchor_path = project_service.anchor_path_for(project_id, stored)
            file_service.delete_file(stored.path)

        try:
            task = generation_service.create_extend_task(
                project_id=project_id,
                source_segment_id=source.id,
                action_prompt=action_prompt,
                final_prompt=final_prompt,
                extend_frames=payload.extend_frames,
                source_video_path=source_video,
                model_path=model.path,
                source_info=source_info,
                seed=seed,
                anchor_image_path=anchor_path,
                anchor_frame=payload.anchor_frame,
                anchor_strength=payload.anchor_strength,
                queue_depth=queued,
            )
        except generation_service.GenerationError as exc:
            code = (
                status.HTTP_429_TOO_MANY_REQUESTS
                if exc.code == "queue_full"
                else status.HTTP_409_CONFLICT
            )
            raise HTTPException(status_code=code, detail=str(exc)) from exc

        estimate = video_service.estimate_added(source_info, payload.extend_frames)

    await queue_manager.submit(task.id)
    logger.info(
        "续写任务入队 task=%s project=%s source=%s",
        task.id,
        project_id,
        payload.source_segment_id,
    )

    return ExtendResponse(
        task_id=task.id,
        project_id=project_id,
        source_segment_id=payload.source_segment_id,
        status=task.status,
        message="续写任务已加入本地队列",
        final_prompt=final_prompt,
        estimated_added_seconds=estimate["added_seconds"],
        estimated_added_frames=int(estimate["added_frames"]),
    )
