"""参数校验工具：帧数 8k+1、分辨率白名单、提示词长度等。"""

from __future__ import annotations

import math
import re
from pathlib import Path

from app.core.config import settings


class ValidationError(ValueError):
    """参数不合法，映射为 HTTP 422。"""


def is_valid_frame_count(frames: int) -> bool:
    """LTX 帧数规则：frames = 8k + 1 且为正。"""
    return frames >= 1 and (frames - 1) % 8 == 0


def validate_prompt(prompt: str) -> str:
    text = (prompt or "").strip()
    if not text:
        raise ValidationError("提示词不能为空")
    if len(text) > settings.max_prompt_length:
        raise ValidationError(
            f"提示词最多 {settings.max_prompt_length} 字符，当前 {len(text)}"
        )
    return text


def validate_frames(frames: int) -> int:
    if not is_valid_frame_count(frames):
        raise ValidationError("帧数必须符合 8k+1 规则，例如 9、25、41、49、65、81、97、121")
    if frames not in settings.allowed_frames:
        allowed = "、".join(str(f) for f in settings.allowed_frames)
        raise ValidationError(f"V1 允许的帧数为：{allowed}")
    return frames


def validate_frame_rate(frame_rate: int) -> int:
    if frame_rate not in settings.allowed_frame_rates:
        allowed = "、".join(str(f) for f in settings.allowed_frame_rates)
        raise ValidationError(f"V1 只开放帧率：{allowed}")
    return frame_rate


def validate_resolution(width: int, height: int) -> tuple[int, int]:
    if width <= 0 or height <= 0:
        raise ValidationError("分辨率必须为正整数")
    if (width, height) not in settings.allowed_resolutions:
        allowed = "、".join(f"{w}×{h}" for w, h in settings.allowed_resolutions)
        raise ValidationError(f"V1 允许的分辨率为：{allowed}")
    return width, height


def validate_mode(mode: str) -> str:
    normalized = (mode or "").strip().lower()
    if normalized != "distilled":
        raise ValidationError("V1 只支持 distilled 推理模式")
    return normalized


def validate_task_type(task_type: str) -> str:
    normalized = (task_type or "").strip().upper()
    if normalized not in {"T2V", "I2V"}:
        raise ValidationError("生成模式必须为 T2V 或 I2V")
    return normalized


def validate_seed(seed: int | None) -> int | None:
    if seed is None:
        return None
    # CLI 约定 -1 表示随机；这里统一映射为 None（由 CLI 自行随机）
    if seed == -1:
        return None
    if seed < 0 or seed > 2**63 - 1:
        raise ValidationError("随机种子必须是 0 ~ 2^63-1 的整数，或 -1 表示随机")
    return seed


def display_duration(frames: int, frame_rate: int) -> float:
    if frame_rate <= 0:
        return 0.0
    return round(frames / frame_rate, 3)


_SAFE_NAME = re.compile(r"[^A-Za-z0-9._-]")


def safe_download_name(prompt: str, task_id: str, suffix: str = ".mp4") -> str:
    """由提示词生成安全的下载文件名（仅用于 Content-Disposition，不落盘）。"""
    snippet = _SAFE_NAME.sub("_", (prompt or "").strip())[:40].strip("._-")
    if not snippet:
        snippet = "ltx-video"
    return f"{snippet}-{task_id[:8]}{suffix}"


def human_gb(value: float) -> float:
    return round(value, 1)


def gb_from_bytes(value: int | float) -> float:
    return round(float(value) / (1024**3), 2)


def frames_match_duration_guard(frames: int, frame_rate: int) -> bool:
    """24GB 设备不默认开放超长视频：限制最大 121 帧 / 5 秒左右。"""
    seconds = frames / frame_rate if frame_rate else math.inf
    return frames <= 121 and seconds <= 6.0


def path_is_image(path: Path) -> bool:
    return path.suffix.lower() in {".png", ".jpg", ".jpeg", ".webp"}
