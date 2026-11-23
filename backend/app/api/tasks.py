"""任务列表、详情、取消、删除、日志与 SSE。"""

from __future__ import annotations

import asyncio
import json
import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, Query, Request, status
from fastapi.responses import StreamingResponse

from app.core.paths import assert_within_allowed
from app.db.database import session_scope
from app.db.models import GenerationTask, TaskStatus
from app.db.repositories import TaskRepository
from app.schemas.task import (
    CancelResponse,
    DeleteResponse,
    TaskDetail,
    TaskListResponse,
    TaskLogsResponse,
)
from app.services import file_service
from app.services.task_queue import queue_manager
from app.utils.validators import ValidationError

logger = logging.getLogger(__name__)

router = APIRouter(tags=["tasks"])

VALID_STATUSES = {s.value for s in TaskStatus}


def _load_task(task_id: str) -> GenerationTask:
    with session_scope() as session:
        task = TaskRepository(session).get(task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在"
            )
        session.expunge(task)
    return task


@router.get("/tasks", response_model=TaskListResponse)
def list_tasks(
    status_filter: str | None = Query(None, alias="status"),
    task_type: str | None = Query(None),
    limit: int = Query(20, ge=1, le=100),
    offset: int = Query(0, ge=0),
) -> TaskListResponse:
    if status_filter and status_filter not in VALID_STATUSES:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效的状态筛选值"
        )
    if task_type and task_type.upper() not in {"T2V", "I2V"}:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="无效的类型筛选值"
        )

    from app.api.serializers import to_summary

    with session_scope() as session:
        items, total = TaskRepository(session).list_tasks(
            status=status_filter,
            task_type=task_type.upper() if task_type else None,
            limit=limit,
            offset=offset,
        )
        payload = [to_summary(task) for task in items]

    return TaskListResponse(items=payload, total=total, limit=limit, offset=offset)


@router.get("/tasks/{task_id}", response_model=TaskDetail)
def get_task(task_id: str) -> TaskDetail:
    from app.api.serializers import to_detail

    task = _load_task(task_id)
    preview = None
    if task.log_path and Path(task.log_path).is_file():
        for line in file_service.tail_lines(Path(task.log_path), limit=200):
            if line.startswith("[studio] command:"):
                preview = line[len("[studio] command:") :].strip()
                break
    return to_detail(task, command_preview=preview)


@router.post("/tasks/{task_id}/cancel", response_model=CancelResponse)
async def cancel_task(task_id: str) -> CancelResponse:
    with session_scope() as session:
        task = TaskRepository(session).get(task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在"
            )
        current = task.status

    if current not in {
        TaskStatus.QUEUED.value,
        TaskStatus.STARTING.value,
        TaskStatus.RUNNING.value,
    }:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"当前状态（{current}）不可取消",
        )

    ok, message = await queue_manager.cancel(task_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=message)

    with session_scope() as session:
        task = TaskRepository(session).get(task_id)
        new_status = task.status if task else current

    return CancelResponse(task_id=task_id, status=new_status, message=message)


@router.delete("/tasks/{task_id}", response_model=DeleteResponse)
def delete_task(
    task_id: str,
    delete_output: bool = Query(True),
) -> DeleteResponse:
    with session_scope() as session:
        repo = TaskRepository(session)
        task = repo.get(task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在"
            )
        if task.status not in (
            TaskStatus.SUCCEEDED.value,
            TaskStatus.FAILED.value,
            TaskStatus.CANCELED.value,
        ):
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail="任务仍在进行中，请先取消再删除",
            )
        output_path = task.output_path
        log_path = task.log_path
        output_exists = bool(output_path and Path(output_path).is_file())

        # 被创作项目版本引用的视频不允许随任务一起物理删除
        referenced = False
        if output_path:
            from app.db.project_repositories import SegmentRepository

            referenced = SegmentRepository(session).is_video_referenced(output_path)

        deleted_output = False
        if delete_output and output_exists and not referenced:
            try:
                safe_output = assert_within_allowed(Path(output_path))
                deleted_output = file_service.delete_file(safe_output)
            except (ValidationError, ValueError, OSError) as exc:
                logger.warning("删除输出文件失败 %s：%s", output_path, exc)
        elif referenced:
            logger.info("输出视频被创作项目引用，保留文件：%s", output_path)

        if log_path:
            try:
                safe_log = assert_within_allowed(Path(log_path))
                file_service.delete_file(safe_log)
            except (ValidationError, ValueError, OSError) as exc:
                logger.warning("删除日志文件失败 %s：%s", log_path, exc)

        repo.delete(task)

    return DeleteResponse(
        task_id=task_id,
        deleted_output=deleted_output,
        message="任务已删除",
    )


@router.get("/tasks/{task_id}/logs", response_model=TaskLogsResponse)
def get_logs(
    task_id: str,
    lines: int = Query(200, ge=1, le=2000),
) -> TaskLogsResponse:
    task = _load_task(task_id)
    if not task.log_path:
        return TaskLogsResponse(
            task_id=task_id, lines=[], total_lines=0, status=task.status
        )

    try:
        log_file = assert_within_allowed(Path(task.log_path))
    except (ValidationError, ValueError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="日志路径非法"
        ) from None

    tail = file_service.tail_lines(log_file, limit=lines)
    total = file_service.count_lines(log_file)
    return TaskLogsResponse(
        task_id=task_id, lines=tail, total_lines=total, status=task.status
    )


@router.get("/tasks/{task_id}/events")
async def task_events(task_id: str, request: Request) -> StreamingResponse:
    """SSE：推送状态变化与新增日志。前端断开可重连。"""
    _load_task(task_id)

    async def event_stream():
        seen_lines = 0
        last_status: str | None = None
        empty_cycles = 0
        yield _sse("hello", {"task_id": task_id})

        while True:
            if await request.is_disconnected():
                break
            try:
                with session_scope() as session:
                    task = TaskRepository(session).get(task_id)
                    if task is None:
                        yield _sse("deleted", {"task_id": task_id})
                        break
                    current_status = task.status
                    log_path = task.log_path
            except Exception:  # pragma: no cover
                logger.exception("SSE 读取任务失败 %s", task_id)
                break

            payload: dict = {"status": current_status}
            if current_status != last_status:
                last_status = current_status
                payload["changed"] = True

            if log_path and Path(log_path).is_file():
                try:
                    safe_log = assert_within_allowed(Path(log_path))
                    all_lines = file_service.tail_lines(safe_log, limit=1000)
                    if len(all_lines) < seen_lines:
                        seen_lines = 0  # 日志被轮转/截断
                    new_lines = all_lines[seen_lines:]
                    if new_lines:
                        seen_lines = len(all_lines)
                        payload["lines"] = new_lines
                except (ValidationError, ValueError, OSError):
                    pass

            yield _sse("update", payload)

            if current_status in {
                TaskStatus.SUCCEEDED.value,
                TaskStatus.FAILED.value,
                TaskStatus.CANCELED.value,
            }:
                empty_cycles += 1
                if empty_cycles >= 2:
                    yield _sse("final", {"status": current_status})
                    break

            await asyncio.sleep(2)

    return StreamingResponse(
        event_stream(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


def _sse(event: str, data: dict) -> str:
    return f"event: {event}\ndata: {json.dumps(data, ensure_ascii=False)}\n\n"


# ---- 应用日志：仅暴露固定的 logs/app.log，不接受任意路径 ----
@router.get("/system/logs", response_model=TaskLogsResponse)
def system_logs(lines: int = Query(200, ge=1, le=2000)) -> TaskLogsResponse:
    from app.core.config import settings

    log_file = settings.logs / "app.log"
    tail = file_service.tail_lines(log_file, limit=lines)
    total = file_service.count_lines(log_file)
    return TaskLogsResponse(
        task_id="system", lines=tail, total_lines=total, status="RUNNING"
    )
