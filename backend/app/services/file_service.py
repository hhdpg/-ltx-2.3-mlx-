"""上传与输出文件管理：真实类型校验、UUID 命名、路径安全。"""

from __future__ import annotations

import logging
import uuid
from dataclasses import dataclass
from pathlib import Path

from PIL import Image, UnidentifiedImageError

from app.core.config import settings
from app.core.paths import assert_within_allowed, safe_join

logger = logging.getLogger(__name__)

ALLOWED_EXTENSIONS = {".png", ".jpg", ".jpeg", ".webp"}
ALLOWED_FORMATS = {"PNG", "JPEG", "WEBP"}
# 允许的魔数前缀
_MAGIC = (
    b"\x89PNG\r\n\x1a\n",  # PNG
    b"\xff\xd8\xff",  # JPEG
    b"RIFF",  # WEBP (RIFF....WEBP)
)
# 明确拒绝的危险类型（与允许类型做黑名单区分）
_FORBIDDEN_EXTENSIONS = {
    ".svg",
    ".svgz",
    ".html",
    ".htm",
    ".js",
    ".mjs",
    ".sh",
    ".py",
    ".php",
    ".exe",
    ".dll",
    ".bat",
    ".cmd",
    ".xml",
}


class UploadError(ValueError):
    """上传失败，error_code 用于映射 HTTP 状态。"""

    def __init__(self, message: str, error_code: str = "invalid_upload") -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass
class StoredUpload:
    upload_id: str
    path: Path
    filename: str
    size: int
    width: int | None
    height: int | None
    content_type: str


def _max_bytes() -> int:
    return settings.max_upload_mb * 1024 * 1024


def save_upload(data: bytes, original_name: str) -> StoredUpload:
    """校验并保存上传图片。拒绝伪装成图片的文件。"""
    if not data:
        raise UploadError("上传文件为空", "empty_file")
    if len(data) > _max_bytes():
        raise UploadError(
            f"上传文件超过 {settings.max_upload_mb} MB 限制", "file_too_large"
        )

    suffix = Path(original_name or "").suffix.lower()
    if suffix in _FORBIDDEN_EXTENSIONS:
        raise UploadError(f"不支持的文件类型：{suffix}", "unsupported_type")
    if suffix not in ALLOWED_EXTENSIONS:
        raise UploadError(
            "仅支持 PNG、JPG、JPEG、WEBP 图片", "unsupported_type"
        )

    if not _looks_like_image(data):
        raise UploadError("文件内容不是有效的图片", "unsupported_type")

    upload_id = uuid.uuid4().hex
    target_name = f"{upload_id}{'.jpg' if suffix in {'.jpg', '.jpeg'} else suffix}"
    settings.uploads.mkdir(parents=True, exist_ok=True)
    target = safe_join(settings.uploads, target_name)

    # 先用 Pillow 完整解码，确认不是伪装文件
    try:
        with Image.open(_bytes_io(data)) as probe:
            probe.verify()
        with Image.open(_bytes_io(data)) as img:
            img.load()
            fmt = (img.format or "").upper()
            width, height = img.size
    except (UnidentifiedImageError, OSError, ValueError) as exc:
        raise UploadError(f"无法解析图片：{exc}", "unsupported_type") from exc

    if fmt not in ALLOWED_FORMATS:
        raise UploadError(f"不支持的图片格式：{fmt or 'unknown'}", "unsupported_type")

    target.write_bytes(data)
    content_type = {
        "PNG": "image/png",
        "JPEG": "image/jpeg",
        "WEBP": "image/webp",
    }.get(fmt, "application/octet-stream")

    logger.info("已保存上传图片 id=%s size=%s dim=%sx%s", upload_id, len(data), width, height)
    return StoredUpload(
        upload_id=upload_id,
        path=target,
        filename=original_name or target_name,
        size=len(data),
        width=width,
        height=height,
        content_type=content_type,
    )


def _bytes_io(data: bytes):
    import io

    return io.BytesIO(data)


def _looks_like_image(data: bytes) -> bool:
    if data.startswith(_MAGIC[0]) or data.startswith(_MAGIC[1]):
        return True
    if data[:4] == b"RIFF" and data[8:12] == b"WEBP":
        return True
    return False


def resolve_upload(upload_id: str) -> Path | None:
    """根据 upload_id 找到已保存的图片（不接受任意路径）。"""
    if not upload_id or "/" in upload_id or ".." in upload_id:
        return None
    for suffix in (".png", ".jpg", ".jpeg", ".webp"):
        candidate = settings.uploads / f"{upload_id}{suffix}"
        if candidate.is_file():
            return candidate.resolve()
    return None


def resolve_allowed(path_str: str | None, expected: str) -> Path | None:
    """把数据库中的路径解析回受控目录内路径，防止被篡改后越界读取。"""
    if not path_str:
        return None
    try:
        resolved = assert_within_allowed(Path(path_str))
    except Exception:
        logger.warning("拒绝访问越界路径：%s", path_str)
        return None
    if expected == "outputs":
        try:
            resolved.relative_to(settings.outputs.resolve())
        except ValueError:
            return None
    elif expected == "uploads":
        try:
            resolved.relative_to(settings.uploads.resolve())
        except ValueError:
            return None
    return resolved if resolved.is_file() else None


def output_ready(path_str: str | None) -> tuple[bool, str | None]:
    """输出文件必须存在且大于 0 字节才算成功。"""
    if not path_str:
        return False, "未生成输出文件"
    path = Path(path_str)
    if not path.is_file():
        return False, f"输出文件不存在：{path}"
    size = path.stat().st_size
    if size <= 0:
        return False, "输出文件大小为 0"
    try:
        path.resolve().relative_to(settings.outputs.resolve())
    except ValueError:
        return False, "输出文件不在允许的输出目录内"
    return True, None


def tail_lines(path: Path, limit: int = 200, max_bytes: int = 512 * 1024) -> list[str]:
    """高效读取文件末尾若干行。"""
    if not path.is_file():
        return []
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > max_bytes:
            handle.seek(-max_bytes, 2)
            handle.readline()  # 丢弃可能被截断的首行
        raw = handle.read()
    lines = raw.decode("utf-8", errors="replace").splitlines()
    if limit <= 0:
        return []
    return lines[-limit:]


def count_lines(path: Path, max_bytes: int = 1024 * 1024) -> int:
    if not path.is_file():
        return 0
    size = path.stat().st_size
    with path.open("rb") as handle:
        if size > max_bytes:
            handle.seek(-max_bytes, 2)
            handle.readline()
        return handle.read().count(b"\n")


def delete_file(path: Path | None) -> bool:
    if path is None:
        return False
    try:
        if path.is_file():
            path.unlink()
            return True
    except OSError as exc:
        logger.warning("删除文件失败 %s：%s", path, exc)
    return False


def image_in_use(image_path: str | None, session) -> bool:
    """检查图片是否被未结束的任务使用。"""
    from sqlalchemy import select

    from app.db.models import GenerationTask
    from app.db.repositories import ACTIVE_STATUSES

    if not image_path or session is None:
        return False
    stmt = select(GenerationTask.id).where(
        GenerationTask.image_path == image_path,
        GenerationTask.status.in_(ACTIVE_STATUSES),
    )
    return session.execute(stmt).first() is not None
