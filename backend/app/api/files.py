"""文件接口：视频流（支持 Range）、下载、上传预览。"""

from __future__ import annotations

import logging
import mimetypes
import re
from pathlib import Path

from fastapi import APIRouter, File, HTTPException, Request, UploadFile, status
from fastapi.responses import FileResponse, Response, StreamingResponse

from app.core.config import settings
from app.core.paths import assert_within_allowed
from app.db.database import session_scope
from app.db.models import TaskStatus
from app.db.repositories import TaskRepository
from app.schemas.task import UploadResponse
from app.services import file_service
from app.utils.validators import safe_download_name

logger = logging.getLogger(__name__)

router = APIRouter(tags=["files"])

_RANGE_RE = re.compile(r"bytes=(?P<start>\d*)-(?P<end>\d*)")
_CHUNK = 256 * 1024
_IMAGE_MIME = {
    ".png": "image/png",
    ".jpg": "image/jpeg",
    ".jpeg": "image/jpeg",
    ".webp": "image/webp",
}


def _output_for_task(task_id: str) -> tuple[Path, str]:
    with session_scope() as session:
        task = TaskRepository(session).get(task_id)
        if task is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="任务不存在"
            )
        if task.status != TaskStatus.SUCCEEDED.value:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT, detail="任务尚未成功生成视频"
            )
        output_path = task.output_path
        prompt = task.prompt

    if not output_path:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="没有输出文件")

    try:
        path = assert_within_allowed(Path(output_path))
    except (ValueError, OSError):
        logger.warning("拒绝访问越界输出路径 task=%s", task_id)
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="输出文件路径非法"
        ) from None

    if not path.is_file() or path.stat().st_size <= 0:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="输出文件不存在或为空"
        )
    return path, prompt


def _segment_path(segment_id: str) -> Path:
    from app.db.models import GenerationSegment

    with session_scope() as session:
        segment = session.get(GenerationSegment, segment_id)
        if segment is None:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND, detail="版本不存在"
            )
        video_path = segment.video_path

    path = file_service.resolve_allowed(video_path, "outputs")
    if path is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND, detail="版本视频不存在或不可访问"
        )
    return path


@router.get("/segments/{segment_id}/video")
def stream_segment_video(segment_id: str, request: Request):
    path = _segment_path(segment_id)
    return _range_response(path, request, media_type="video/mp4", inline=True)


@router.get("/segments/{segment_id}/download")
def download_segment_video(segment_id: str):
    path = _segment_path(segment_id)
    filename = f"segment-{segment_id[:8]}.mp4"
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


@router.get("/files/{task_id}/video")
def stream_video(task_id: str, request: Request):
    path, _ = _output_for_task(task_id)
    return _range_response(path, request, media_type="video/mp4", inline=True)


@router.get("/files/{task_id}/download")
def download_video(task_id: str):
    path, prompt = _output_for_task(task_id)
    filename = safe_download_name(prompt, task_id)
    return FileResponse(
        path,
        media_type="video/mp4",
        filename=filename,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )


def _range_response(path: Path, request: Request, media_type: str, inline: bool):
    file_size = path.stat().st_size
    range_header = request.headers.get("range") or request.headers.get("Range")

    if not range_header:
        return FileResponse(
            path,
            media_type=media_type,
            headers={
                "Accept-Ranges": "bytes",
                "Content-Length": str(file_size),
            },
        )

    match = _RANGE_RE.fullmatch(range_header.strip())
    if not match:
        return Response(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    start_raw = match.group("start")
    end_raw = match.group("end")
    if start_raw:
        start = int(start_raw)
        end = int(end_raw) if end_raw else file_size - 1
    elif end_raw:  # bytes=-N 表示最后 N 字节
        tail = int(end_raw)
        start = max(file_size - tail, 0)
        end = file_size - 1
    else:
        return Response(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{file_size}"},
        )

    if start >= file_size or start > end:
        return Response(
            status_code=status.HTTP_416_REQUESTED_RANGE_NOT_SATISFIABLE,
            headers={"Content-Range": f"bytes */{file_size}"},
        )
    end = min(end, file_size - 1)
    length = end - start + 1

    def iterator():
        with path.open("rb") as handle:
            handle.seek(start)
            remaining = length
            while remaining > 0:
                chunk = handle.read(min(_CHUNK, remaining))
                if not chunk:
                    break
                remaining -= len(chunk)
                yield chunk

    return StreamingResponse(
        iterator(),
        status_code=status.HTTP_206_PARTIAL_CONTENT,
        media_type=media_type,
        headers={
            "Content-Range": f"bytes {start}-{end}/{file_size}",
            "Accept-Ranges": "bytes",
            "Content-Length": str(length),
        },
    )


@router.get("/files/uploads/{filename}")
def get_upload(filename: str):
    if "/" in filename or "\\" in filename or ".." in filename:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="非法文件名")
    try:
        path = assert_within_allowed(Path(filename), roots=(settings.uploads,))
    except (ValueError, OSError):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST, detail="非法文件路径"
        ) from None
    if not path.is_file():
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="图片不存在")

    media_type, _ = mimetypes.guess_type(str(path))
    if path.suffix.lower() in _IMAGE_MIME:
        media_type = _IMAGE_MIME[path.suffix.lower()]
    return FileResponse(path, media_type=media_type or "application/octet-stream")


@router.post("/files/upload", response_model=UploadResponse)
async def upload_image(image: UploadFile = File(...)) -> UploadResponse:
    """独立上传接口：先上传后引用（V1 主流程仍支持随任务一起上传）。"""
    data = await image.read()
    try:
        stored = file_service.save_upload(data, image.filename or "upload")
    except file_service.UploadError as exc:
        code = {
            "file_too_large": status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
            "unsupported_type": status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        }.get(exc.error_code, status.HTTP_422_UNPROCESSABLE_ENTITY)
        raise HTTPException(status_code=code, detail=str(exc)) from exc

    return UploadResponse(
        upload_id=stored.upload_id,
        filename=stored.filename,
        size=stored.size,
        width=stored.width,
        height=stored.height,
        content_type=stored.content_type,
        preview_url=f"/api/files/uploads/{stored.path.name}",
    )
