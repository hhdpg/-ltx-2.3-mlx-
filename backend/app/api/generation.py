"""生成任务提交接口（multipart/form-data）。"""

from __future__ import annotations

import logging

from fastapi import APIRouter, File, Form, HTTPException, UploadFile, status
from sqlalchemy import func, select

from app.core.config import settings
from app.db.database import session_scope
from app.db.models import GenerationTask
from app.db.repositories import TaskRepository
from app.schemas.generation import GenerationParams
from app.schemas.task import CreateTaskResponse
from app.services import file_service, generation_service, model_service
from app.services.task_queue import queue_manager
from app.utils.validators import ValidationError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["generation"])


def _check_ready() -> str | None:
    """提交前置检查，返回阻断原因（None 表示可提交）。"""
    model = model_service.effective_model()
    if model.status == "error":
        return model.message
    if not settings.cli_available:
        return f"推理 CLI 不可用：{settings.ltx_executable or '未配置 LTX_EXECUTABLE'}"
    return None


@router.post(
    "/generations",
    response_model=CreateTaskResponse,
    status_code=status.HTTP_202_ACCEPTED,
)
async def create_generation(
    task_type: str = Form(...),
    prompt: str = Form(...),
    width: int = Form(...),
    height: int = Form(...),
    frames: int = Form(...),
    frame_rate: int = Form(...),
    mode: str = Form("distilled"),
    seed: str | None = Form(None),
    project_id: str | None = Form(None),
    image: UploadFile | None = File(None),
) -> CreateTaskResponse:
    blocked = _check_ready()
    if blocked:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=blocked)

    # 可选：直接为某个创作项目生成首段（任务成功后自动创建版本）
    target_project_id: str | None = None
    if project_id:
        from app.db.project_repositories import ProjectRepository

        with session_scope() as session:
            project = ProjectRepository(session).get(project_id)
            if project is None:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND, detail="项目不存在"
                )
        target_project_id = project_id

    with session_scope() as session:
        queued = session.execute(
            select(func.count(GenerationTask.id)).where(
                GenerationTask.status == "QUEUED"
            )
        ).scalar_one()
    if queued >= settings.max_queue_size:
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail=f"队列已满（最多 {settings.max_queue_size} 个等待任务），请稍后再试",
        )

    try:
        parsed_seed = int(seed) if seed not in (None, "", "null", "random") else None
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="随机种子必须是整数",
        ) from None

    try:
        params = GenerationParams.validated(
            task_type=task_type,
            prompt=prompt,
            width=width,
            height=height,
            frames=frames,
            frame_rate=frame_rate,
            mode=mode,
            seed=parsed_seed,
        )
    except ValidationError as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
        ) from exc

    image_path = None
    if params.task_type == "I2V":
        if image is None:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail="图片生成模式必须上传一张参考图片",
            )
        try:
            data = await image.read()
            stored = file_service.save_upload(data, image.filename or "upload")
        except file_service.UploadError as exc:
            code = {
                "file_too_large": status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                "unsupported_type": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
            }.get(exc.error_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
            raise HTTPException(status_code=code, detail=str(exc)) from exc
        image_path = stored.path
    elif image is not None:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="文字生成模式不应上传参考图片",
        )

    model = model_service.effective_model()
    if model.path is None:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT, detail=model.message or "模型未配置"
        )

    try:
        task = generation_service.create_task(
            params,
            image_path=image_path,
            model_path=model.path,
            queue_depth=queued,
            project_id=target_project_id,
        )
    except generation_service.GenerationError as exc:
        code = (
            status.HTTP_429_TOO_MANY_REQUESTS
            if exc.code == "queue_full"
            else status.HTTP_409_CONFLICT
        )
        raise HTTPException(status_code=code, detail=str(exc)) from exc

    await queue_manager.submit(task.id)
    logger.info("任务已入队 id=%s type=%s", task.id, task.task_type)

    return CreateTaskResponse(
        task_id=task.id,
        status=task.status,
        message="任务已加入队列",
    )
