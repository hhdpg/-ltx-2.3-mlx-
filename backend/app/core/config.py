"""应用配置：全部路径通过环境变量提供，禁止在业务代码中硬编码。"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

BACKEND_DIR = Path(__file__).resolve().parents[2]
DEFAULT_PROJECT_ROOT = BACKEND_DIR.parent


def _abs_path(value: str | Path | None) -> Path | None:
    """展开 ~ 并解析为绝对路径（不跟踪符号链接）。空值返回 None。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return Path(os.path.abspath(os.path.expanduser(text)))


def _real_path(value: str | Path | None) -> Path | None:
    """展开 ~ 并解析为绝对路径，同时跟踪符号链接（用于普通目录）。"""
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    return Path(text).expanduser().resolve()


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=(
            str(BACKEND_DIR / ".env"),
            str(DEFAULT_PROJECT_ROOT / ".env"),
        ),
        env_file_encoding="utf-8",
        extra="ignore",
        case_sensitive=False,
    )

    app_name: str = "LTX Local Studio"
    app_env: str = "local"
    app_host: str = "127.0.0.1"
    app_port: int = 8000

    project_root: Path = DEFAULT_PROJECT_ROOT

    # ---- 推理侧（由用户机器上的实际安装决定）----
    ltx_project_root: Path | None = None
    ltx_executable: Path | None = None
    ltx_python: Path | None = None
    ltx_model_id: str = "dgrauet/ltx-2.3-mlx-q4"
    ltx_model_path: Path | None = None
    ltx_mode: str = "distilled"
    ltx_low_ram: bool = False

    # ---- 存储 ----
    upload_dir: Path | None = None
    output_dir: Path | None = None
    log_dir: Path | None = None
    database_url: str | None = None

    # ---- 运行约束 ----
    hf_hub_offline: bool = True
    transformers_offline: bool = True

    max_upload_mb: int = 15
    max_prompt_length: int = 4000
    max_queue_size: int = 10
    generation_timeout_seconds: int = 7200

    # 单任务队列 / 进程管理
    cancel_grace_seconds: float = 8.0
    min_free_disk_gb: float = 2.0
    warn_free_memory_gb: float = 2.0
    min_free_memory_gb: float = 0.5

    # 帧数 / 分辨率白名单（后端硬校验）
    allowed_frames: tuple[int, ...] = (9, 25, 41, 49, 65, 81, 97, 121)
    allowed_frame_rates: tuple[int, ...] = (24,)
    allowed_resolutions: tuple[tuple[int, int], ...] = (
        (512, 320),
        (320, 512),
        (640, 384),
        (384, 640),
        (768, 512),
        (512, 768),
    )
    default_width: int = 512
    default_height: int = 320
    default_frames: int = 25
    default_frame_rate: int = 24

    # I2V 图片条件参数默认值（Frame / Strength / Mode），随本机 CLI --help 调整
    image_frame: int = 0
    image_strength: float = 1.0
    image_mode: str = "auto"

    # 本机 ltx-2-mlx v0.18.0 的 generate 已支持 --seed / -s
    seed_supported: bool = True

    # ---- V1.1 连续续写（extend）----
    # extend_frames 是新增 latent frames；新增视频帧数 = 8 × extend_frames
    # 本机实测：1/2/4/8 均可完成；12 为 24GB 内存下的保守上限
    allowed_extend_frames: tuple[int, ...] = (1, 2, 4, 8, 12)
    default_extend_frames: int = 4
    # extend 的 --image 锚点默认强度（FRAME_IDX 由请求指定）
    anchor_default_strength: float = 1.0
    anchor_default_frame: int = 0

    # ---- 跨域（仅本地开发）----
    cors_origins: list[str] = Field(
        default_factory=lambda: [
            "http://127.0.0.1:5173",
            "http://localhost:5173",
        ]
    )

    @field_validator(
        "project_root",
        "ltx_model_path",
        "upload_dir",
        "output_dir",
        "log_dir",
        mode="before",
    )
    @classmethod
    def _resolve_dirs(cls, value):
        return _real_path(value) if value is not None else None

    @field_validator("ltx_project_root", "ltx_executable", "ltx_python", mode="before")
    @classmethod
    def _resolve_exec(cls, value):
        # 可执行文件/虚拟环境路径不跟踪符号链接：venv 的 python 是软链，
        # 跟踪后会退出虚拟环境导致 import mlx 失败。
        return _abs_path(value) if value is not None else None

    @field_validator("ltx_mode")
    @classmethod
    def _check_mode(cls, value: str) -> str:
        normalized = (value or "").strip().lower()
        if normalized not in {"distilled"}:
            raise ValueError("V1 仅支持 distilled 推理模式")
        return normalized

    # ---- 派生路径 ----
    @property
    def root(self) -> Path:
        return self.project_root

    @property
    def data_dir(self) -> Path:
        return self.root / "data"

    @property
    def uploads(self) -> Path:
        return self.upload_dir or (self.root / "uploads")

    @property
    def outputs(self) -> Path:
        return self.output_dir or self.root / "output"

    @property
    def logs(self) -> Path:
        return self.log_dir or self.root / "logs"

    @property
    def task_log_dir(self) -> Path:
        return self.logs / "tasks"

    @property
    def sqlalchemy_url(self) -> str:
        if self.database_url:
            url = self.database_url.strip()
            if url.startswith("sqlite:///"):
                raw = url[len("sqlite:///") :]
                path = Path(raw).expanduser()
                if not path.is_absolute():
                    # 相对路径统一相对项目根目录解析，避免受启动 cwd 影响
                    path = (self.project_root / path).resolve()
                else:
                    path = path.resolve()
                return f"sqlite:///{path}"
            return url
        return f"sqlite:///{self.data_dir / 'studio.db'}"

    @property
    def db_path(self) -> Path:
        url = self.sqlalchemy_url
        if url.startswith("sqlite:///"):
            return Path(url[len("sqlite:///") :])
        raise ValueError("当前仅支持 SQLite 数据库")

    @property
    def cli_available(self) -> bool:
        exe = self.ltx_executable
        return bool(exe and exe.is_file() and exe.stat().st_mode & 0o111)


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    return Settings()


settings = get_settings()
