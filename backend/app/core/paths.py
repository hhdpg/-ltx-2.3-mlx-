"""路径工具：目录初始化与子路径安全校验（防目录穿越）。"""

from __future__ import annotations

from pathlib import Path

from app.core.config import settings


class UnsafePathError(ValueError):
    """路径越出允许的根目录。"""


MANAGED_DIRS = (
    "data",
    "uploads",
    "outputs",
    "logs",
)


def ensure_directories() -> dict[str, Path]:
    """创建所有运行所需目录，返回目录映射。"""
    mapping = {
        "data": settings.data_dir,
        "uploads": settings.uploads,
        "outputs": settings.outputs,
        "logs": settings.logs,
        "task_logs": settings.task_log_dir,
    }
    for path in mapping.values():
        path.mkdir(parents=True, exist_ok=True)
    return mapping


def _within(candidate: Path, root: Path) -> bool:
    try:
        candidate.relative_to(root)
        return True
    except ValueError:
        return False


def safe_join(root: Path, name: str) -> Path:
    """把 name 拼到 root 下；若越出 root（含 ../ 或绝对路径）则抛错。"""
    if not name or name.startswith(("/", "\\")):
        raise UnsafePathError(f"非法文件名: {name!r}")
    if ".." in Path(name).parts:
        raise UnsafePathError(f"非法文件名: {name!r}")

    root_resolved = root.resolve()
    candidate = (root_resolved / name).resolve()
    if candidate != root_resolved and not _within(candidate, root_resolved):
        raise UnsafePathError(f"路径越界: {name!r}")
    return candidate


def assert_within_allowed(path: Path, roots: tuple[Path, ...] | None = None) -> Path:
    """校验 path 必须位于允许目录内，返回解析后的绝对路径。"""
    allowed = roots or (settings.uploads, settings.outputs, settings.task_log_dir)
    resolved = path.resolve()
    for root in allowed:
        try:
            resolved.relative_to(root.resolve())
            return resolved
        except ValueError:
            continue
    raise UnsafePathError(f"不允许访问的路径: {path}")


def upload_path(filename: str) -> Path:
    return safe_join(settings.uploads, filename)


def output_path(filename: str) -> Path:
    return safe_join(settings.outputs, filename)


def task_log_path(filename: str) -> Path:
    return safe_join(settings.task_log_dir, filename)
