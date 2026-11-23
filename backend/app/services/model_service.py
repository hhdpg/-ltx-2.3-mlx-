"""模型路径解析与完整性检查。

路径优先级：
  1. .env 中的 LTX_MODEL_PATH
  2. 设置页保存的本地模型目录（app_setting.model_path）
  3. Hugging Face 本地缓存（local_files_only=True，绝不联网查找）
  4. 未配置 → 禁止提交任务
"""

from __future__ import annotations

import logging
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings
from app.db.database import session_scope
from app.db.repositories import SettingRepository

logger = logging.getLogger(__name__)

SETTING_MODEL_PATH = "model_path"

# 权重/配置类文件后缀：至少命中一个且大小 > 0
WEIGHT_SUFFIXES = (
    ".safetensors",
    ".npz",
    ".bin",
    ".gguf",
    ".pt",
    ".pth",
    ".json",
)

CORE_CONFIG_NAMES = (
    "model_index.json",
    "config.json",
    "config.yaml",
    "config.yml",
)


@dataclass
class ModelCheckResult:
    configured: bool
    path: Path | None = None
    source: str | None = None
    complete: bool = False
    status: str = "error"  # ok | warn | error
    message: str = ""
    weight_files: int = 0
    total_bytes: int = 0
    missing: list[str] = field(default_factory=list)

    @property
    def error(self) -> str | None:
        return None if self.status == "ok" else (self.message or "模型不可用")


def saved_model_path() -> Path | None:
    try:
        with session_scope() as session:
            raw = SettingRepository(session).get(SETTING_MODEL_PATH)
    except Exception as exc:  # pragma: no cover - 数据库异常不应阻断启动
        logger.warning("读取设置中的模型路径失败：%s", exc)
        return None
    if not raw:
        return None
    path = Path(raw).expanduser()
    return path.resolve() if path.exists() else path


def save_model_path(path: str | None) -> None:
    with session_scope() as session:
        repo = SettingRepository(session)
        if path:
            repo.set(SETTING_MODEL_PATH, str(Path(path).expanduser().resolve()))
        else:
            repo.delete(SETTING_MODEL_PATH)


def resolve_model_path() -> tuple[Path | None, str | None]:
    """返回 (路径, 来源)。来源：env | setting | hf_cache。"""
    if settings.ltx_model_path:
        return settings.ltx_model_path, "env"

    configured = saved_model_path()
    if configured:
        return configured, "setting"

    cached = _hf_cache_snapshot()
    if cached:
        return cached, "hf_cache"
    return None, None


def _hf_cache_snapshot() -> Path | None:
    """仅在本地缓存中查找快照目录，全程离线。"""
    repo_id = (settings.ltx_model_id or "").strip()
    if not repo_id:
        return None
    try:
        from huggingface_hub import snapshot_download
    except ImportError:
        logger.debug("未安装 huggingface_hub，跳过缓存查找")
        return None

    try:
        path = snapshot_download(
            repo_id=repo_id,
            local_files_only=True,
            allow_patterns=None,
        )
    except Exception as exc:
        logger.debug("本地缓存未找到模型 %s：%s", repo_id, exc)
        return None
    return Path(path).resolve()


def check_model_path(path: Path | None) -> ModelCheckResult:
    """检查目录存在性、核心配置与权重文件大小。"""
    if path is None:
        return ModelCheckResult(
            configured=False,
            status="error",
            message="模型未配置：请在设置页选择本地模型目录或在 .env 中设置 LTX_MODEL_PATH",
        )

    if not path.exists():
        return ModelCheckResult(
            configured=True,
            path=path,
            status="error",
            message=f"模型目录不存在：{path}",
            missing=[str(path)],
        )
    if not path.is_dir():
        return ModelCheckResult(
            configured=True,
            path=path,
            status="error",
            message=f"模型路径不是目录：{path}",
        )

    total_bytes = 0
    weight_files = 0
    empty_weights: list[str] = []
    configs: set[str] = set()

    try:
        for entry in path.rglob("*"):
            if not entry.is_file():
                continue
            name = entry.name
            if name in CORE_CONFIG_NAMES:
                configs.add(name)
            if entry.suffix.lower() in WEIGHT_SUFFIXES:
                size = entry.stat().st_size
                total_bytes += size
                if size > 0:
                    weight_files += 1
                else:
                    empty_weights.append(str(entry.relative_to(path)))
    except OSError as exc:
        return ModelCheckResult(
            configured=True,
            path=path,
            status="error",
            message=f"读取模型目录失败：{exc}",
        )

    if weight_files == 0:
        return ModelCheckResult(
            configured=True,
            path=path,
            status="error",
            message="模型目录中未找到非空权重文件，请检查模型文件是否下载完整",
            missing=empty_weights[:10],
        )

    if not configs:
        return ModelCheckResult(
            configured=True,
            path=path,
            source=None,
            complete=True,
            status="warn",
            message="未找到核心配置文件（model_index.json / config.json），请确认目录是否为模型根目录",
            weight_files=weight_files,
            total_bytes=total_bytes,
        )

    if empty_weights:
        return ModelCheckResult(
            configured=True,
            path=path,
            complete=True,
            status="warn",
            message=f"发现 {len(empty_weights)} 个 0 字节权重文件，模型可能不完整",
            weight_files=weight_files,
            total_bytes=total_bytes,
            missing=empty_weights[:10],
        )

    return ModelCheckResult(
        configured=True,
        path=path,
        complete=True,
        status="ok",
        message=f"模型目录可用（{weight_files} 个权重文件，共 {total_bytes / 1024**3:.1f} GiB）",
        weight_files=weight_files,
        total_bytes=total_bytes,
    )


def effective_model() -> ModelCheckResult:
    """解析并检查当前生效的模型。"""
    path, source = resolve_model_path()
    result = check_model_path(path)
    result.source = source
    return result


def model_usable() -> tuple[bool, str | None, Path | None]:
    result = effective_model()
    if result.status == "error":
        return False, result.message, result.path
    return True, None, result.path
