"""视频探测：用 ffprobe 读取尺寸 / 帧率 / 时长 / 帧数，并校验 Extend 约束。"""

from __future__ import annotations

import json
import logging
import shutil
import subprocess
from dataclasses import dataclass
from fractions import Fraction
from pathlib import Path

from app.core.config import settings

logger = logging.getLogger(__name__)

PROBE_TIMEOUT = 30.0
# Distilled Extend 要求源视频宽高均为 64 的倍数
SIZE_MULTIPLE = 64


class VideoError(RuntimeError):
    def __init__(self, message: str, code: str = "invalid_video") -> None:
        super().__init__(message)
        self.code = code


@dataclass
class VideoInfo:
    path: Path
    width: int
    height: int
    frame_rate: float
    duration: float
    frame_count: int | None
    has_audio: bool

    @property
    def size_ok(self) -> bool:
        return self.width % SIZE_MULTIPLE == 0 and self.height % SIZE_MULTIPLE == 0


def _ffprobe_path() -> str:
    exe = shutil.which("ffprobe")
    if not exe:
        raise VideoError("未找到 ffprobe，请先安装 FFmpeg", "ffprobe_missing")
    return exe


def probe_video(path: Path, *, validate_size: bool = False) -> VideoInfo:
    """读取视频元信息。validate_size=True 时校验 64 倍数约束。"""
    resolved = path.expanduser()
    if not resolved.is_file():
        raise VideoError(f"视频文件不存在：{resolved}", "video_missing")
    if resolved.stat().st_size <= 0:
        raise VideoError("视频文件大小为 0", "video_empty")

    try:
        proc = subprocess.run(  # noqa: S603 - 固定参数数组，无 shell
            [
                _ffprobe_path(),
                "-v",
                "error",
                "-show_entries",
                "stream=codec_type,width,height,r_frame_rate,nb_frames,duration",
                "-show_entries",
                "format=duration",
                "-of",
                "json",
                str(resolved),
            ],
            capture_output=True,
            text=True,
            timeout=PROBE_TIMEOUT,
        )
    except subprocess.TimeoutExpired:
        raise VideoError("ffprobe 读取超时", "video_unreadable") from None
    except OSError as exc:
        raise VideoError(f"无法执行 ffprobe：{exc}", "ffprobe_missing") from exc

    if proc.returncode != 0:
        detail = (proc.stderr or "").strip().splitlines()
        message = detail[-1] if detail else f"退出码 {proc.returncode}"
        raise VideoError(f"视频无法解析：{message}", "video_unreadable")

    try:
        payload = json.loads(proc.stdout or "{}")
    except json.JSONDecodeError:
        raise VideoError("ffprobe 输出无法解析", "video_unreadable") from None

    streams = payload.get("streams") or []
    video_stream = next(
        (s for s in streams if s.get("codec_type") == "video"), None
    )
    if video_stream is None:
        raise VideoError("文件中没有视频流", "video_unreadable")

    has_audio = any(s.get("codec_type") == "audio" for s in streams)

    width = int(video_stream.get("width") or 0)
    height = int(video_stream.get("height") or 0)
    if width <= 0 or height <= 0:
        raise VideoError("无法读取视频分辨率", "video_unreadable")

    frame_rate = _parse_rate(video_stream.get("r_frame_rate"))
    duration = _parse_float(video_stream.get("duration"))
    if duration is None:
        duration = _parse_float((payload.get("format") or {}).get("duration"))
    if duration is None:
        raise VideoError("无法读取视频时长", "video_unreadable")

    frame_count = None
    raw_frames = video_stream.get("nb_frames")
    if raw_frames:
        try:
            frame_count = int(raw_frames)
        except (TypeError, ValueError):
            frame_count = None
    if frame_count is None and frame_rate > 0:
        frame_count = int(round(duration * frame_rate))

    info = VideoInfo(
        path=resolved,
        width=width,
        height=height,
        frame_rate=frame_rate,
        duration=duration,
        frame_count=frame_count,
        has_audio=has_audio,
    )

    if validate_size and not info.size_ok:
        raise VideoError(
            f"源视频尺寸 {width}x{height} 不满足 64 倍数约束"
            f"（需宽高均为 {SIZE_MULTIPLE} 的整数倍），请先生成兼容尺寸的视频",
            "video_size_invalid",
        )
    return info


def _parse_rate(raw) -> float:
    """解析 '24/1' 形式的帧率。"""
    if not raw:
        return 24.0
    text = str(raw)
    try:
        if "/" in text:
            value = float(Fraction(text))
        else:
            value = float(text)
    except (ValueError, ZeroDivisionError):
        return 24.0
    return round(value, 3) if value > 0 else 24.0


def _parse_float(raw) -> float | None:
    if raw is None:
        return None
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return None
    return value if value >= 0 else None


def validate_extend_frames(extend_frames: int) -> int:
    if extend_frames not in settings.allowed_extend_frames:
        allowed = "、".join(str(v) for v in settings.allowed_extend_frames)
        raise VideoError(f"续写长度只能是 {allowed}（单位：latent frames）", "bad_extend")
    return extend_frames


def estimate_added(info: VideoInfo, extend_frames: int) -> dict[str, float]:
    """按源视频真实 FPS 估算新增帧数与时长。"""
    added_frames = extend_frames * 8
    fps = info.frame_rate or 24.0
    return {
        "added_frames": float(added_frames),
        "added_seconds": round(added_frames / fps, 3),
        "total_frames": float((info.frame_count or 0) + added_frames),
    }


# ---------- Retake：视频帧 ↔ latent 帧换算 ----------
# LTX 的视频 latent 压缩为时间 8x：latent 帧数 L 对应视频帧数 8(L-1)+1。
# 因此 latent 索引 i 覆盖视频帧区间 [8i, 8i+8)。
def frames_to_latent(frame_count: int) -> int:
    """视频帧数 → latent 帧数。"""
    if frame_count <= 0:
        return 0
    return (frame_count - 1) // 8 + 1


def latent_to_frames(latent_count: int) -> int:
    """latent 帧数 → 对应的视频帧数。"""
    if latent_count <= 0:
        return 0
    return (latent_count - 1) * 8 + 1


def latent_window_to_seconds(
    start_latent: int, end_latent: int, fps: float
) -> tuple[float, float]:
    """latent 区间 [start, end) → 视频时间区间（秒）。"""
    real_fps = fps if fps > 0 else 24.0
    return (
        round(start_latent * 8 / real_fps, 3),
        round(end_latent * 8 / real_fps, 3),
    )


def seconds_to_latent_index(seconds: float, fps: float) -> int:
    """秒 → 最近的 latent 边界索引（向下取整到 8 帧边界）。"""
    real_fps = fps if fps > 0 else 24.0
    frame = max(0.0, seconds) * real_fps
    return int(frame // 8)


def validate_retake_range(
    info: VideoInfo, start_latent: int, end_latent: int
) -> tuple[int, int]:
    """校验 latent 区间合法且不超过源视频总长。"""
    total_latent = frames_to_latent(info.frame_count or 0)
    if total_latent <= 0:
        raise VideoError("无法确定源视频的 latent 长度", "video_unreadable")
    if start_latent < 0:
        raise VideoError("重拍起始帧不能为负数", "bad_retake_range")
    if end_latent <= start_latent:
        raise VideoError("重拍区间的结束帧必须大于开始帧", "bad_retake_range")
    if end_latent > total_latent:
        raise VideoError(
            f"重拍区间超出源视频长度（该视频共 {total_latent} 个 latent 帧，"
            f"约 {(info.duration or 0):.2f} 秒）",
            "bad_retake_range",
        )
    return start_latent, end_latent


def retake_preview(info: VideoInfo, start_latent: int, end_latent: int) -> dict:
    """返回给前端的区间信息（latent 索引、视频帧、时间）。"""
    total_latent = frames_to_latent(info.frame_count or 0)
    start_sec, end_sec = latent_window_to_seconds(
        start_latent, end_latent, info.frame_rate
    )
    return {
        "start_latent": start_latent,
        "end_latent": end_latent,
        "total_latent": total_latent,
        "start_frame": start_latent * 8,
        "end_frame": min(end_latent * 8, info.frame_count or end_latent * 8),
        "start_seconds": start_sec,
        "end_seconds": end_sec,
        "duration_seconds": round(end_sec - start_sec, 3),
        "source_frames": info.frame_count or 0,
        "source_duration": round(info.duration or 0, 3),
        "fps": info.frame_rate,
    }
