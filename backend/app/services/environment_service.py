"""环境健康检查：汇总 MLX、CLI、模型、FFmpeg、磁盘、内存等状态。"""

from __future__ import annotations

import platform
import shutil
import subprocess
import sys
import time
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import settings
from app.schemas.system import CheckItem
from app.services import model_service
from app.services.mlx_service import cli_help_check, detect_mlx

FFMPEG_PROBE_TIMEOUT = 15.0
_CACHE_TTL = 60.0
_CACHED: "EnvironmentReport | None" = None
_CACHED_AT = 0.0


@dataclass
class EnvironmentReport:
    checks: list[CheckItem] = field(default_factory=list)
    mlx_available: bool = False
    mlx_device: str | None = None
    mlx_error: str | None = None
    cli_available: bool = False
    cli_error: str | None = None
    cli_version: str | None = None
    model_configured: bool = False
    model_path: str | None = None
    model_error: str | None = None
    ffmpeg_available: bool = False
    ffmpeg_error: str | None = None
    disk_total_gb: float | None = None
    disk_free_gb: float | None = None
    total_memory_gb: float | None = None
    available_memory_gb: float | None = None
    blocking_reasons: list[str] = field(default_factory=list)

    @property
    def ready(self) -> bool:
        return not self.blocking_reasons


def _gb(value: float) -> float:
    return round(value / (1024**3), 2)


def disk_usage(path: Path) -> tuple[float | None, float | None]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(path)
        return _gb(usage.total), _gb(usage.free)
    except OSError:
        return None, None


def memory_info() -> tuple[float | None, float | None]:
    """macOS 上通过 vm_stat 估算可用内存，其它平台返回 None。"""
    total = None
    try:
        total = _gb(float(subprocess.run(  # noqa: S603
            ["sysctl", "-n", "hw.memsize"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip()))
    except (ValueError, OSError, subprocess.SubprocessError):
        total = None

    if sys.platform != "darwin":
        return total, None

    try:
        page_size = int(subprocess.run(  # noqa: S603
            ["sysctl", "-n", "hw.pagesize"],
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout.strip())
        vm_stat = subprocess.run(  # noqa: S603
            ["vm_stat"], capture_output=True, text=True, timeout=5
        ).stdout
    except (ValueError, OSError, subprocess.SubprocessError):
        return total, None

    counters: dict[str, int] = {}
    for line in vm_stat.splitlines():
        if ":" not in line:
            continue
        key, _, raw = line.partition(":")
        digits = "".join(ch for ch in raw if ch.isdigit())
        if digits:
            counters[key.strip()] = int(digits)

    free_pages = (
        counters.get("Pages free", 0)
        + counters.get("Pages inactive", 0)
        + counters.get("Pages speculative", 0)
    )
    if not free_pages:
        return total, None
    return total, _gb(free_pages * page_size)


def check_ffmpeg() -> tuple[bool, str | None]:
    exe = shutil.which("ffmpeg")
    if not exe:
        return False, "未找到 ffmpeg，请先安装（brew install ffmpeg）"
    try:
        proc = subprocess.run(  # noqa: S603
            [exe, "-version"],
            capture_output=True,
            text=True,
            timeout=FFMPEG_PROBE_TIMEOUT,
        )
    except (OSError, subprocess.SubprocessError) as exc:
        return False, f"无法执行 ffmpeg：{exc}"
    if proc.returncode != 0:
        return False, f"ffmpeg -version 退出码 {proc.returncode}"
    first = (proc.stdout or "").strip().splitlines()
    return True, first[0] if first else None


def check_writable(path: Path) -> tuple[bool, str | None]:
    try:
        path.mkdir(parents=True, exist_ok=True)
        probe = path / ".write_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink(missing_ok=True)
        return True, None
    except OSError as exc:
        return False, f"目录不可写 {path}：{exc}"


def collect_environment(force: bool = False) -> EnvironmentReport:
    """收集环境状态。检测包含子进程探测，结果缓存 60 秒。"""
    global _CACHED, _CACHED_AT
    now = time.monotonic()
    if not force and _CACHED is not None and now - _CACHED_AT < _CACHE_TTL:
        return _CACHED

    report = _collect()
    _CACHED = report
    _CACHED_AT = now
    return report


def invalidate_cache() -> None:
    global _CACHED
    _CACHED = None


def _collect() -> EnvironmentReport:
    report = EnvironmentReport()
    checks = report.checks

    # ---- macOS ----
    ver = platform.mac_ver()[0]
    is_mac = platform.system() == "Darwin"
    checks.append(
        CheckItem(
            key="macos",
            label="macOS",
            status="ok" if is_mac else "warn",
            message=ver or platform.platform(),
            detail=None if is_mac else "非 macOS 环境，MLX GPU 推理不可用",
        )
    )
    if not is_mac:
        report.blocking_reasons.append("当前系统不是 macOS，MLX 无法使用")

    # ---- CPU 架构 ----
    machine = platform.machine()
    is_arm = machine in {"arm64", "aarch64"}
    checks.append(
        CheckItem(
            key="architecture",
            label="CPU 架构",
            status="ok" if is_arm else "error",
            message=machine or "未知",
        )
    )
    if not is_arm:
        report.blocking_reasons.append("CPU 架构不是 Apple Silicon（arm64）")

    # ---- Python ----
    checks.append(
        CheckItem(
            key="python",
            label="Python",
            status="ok",
            message=platform.python_version(),
        )
    )

    # ---- MLX ----
    mlx = detect_mlx()
    report.mlx_available = mlx.available
    report.mlx_device = mlx.device
    report.mlx_error = mlx.error
    checks.append(
        CheckItem(
            key="mlx",
            label="MLX",
            status="ok" if mlx.available else "error",
            message=mlx.device or mlx.error or "未知",
            detail=mlx.python_path,
        )
    )
    if not mlx.available:
        report.blocking_reasons.append(mlx.error or "MLX 不可用")

    # ---- CLI ----
    cli_ok, cli_err, cli_version = cli_help_check()
    report.cli_available = cli_ok
    report.cli_error = cli_err
    report.cli_version = cli_version
    checks.append(
        CheckItem(
            key="cli",
            label="推理 CLI",
            status="ok" if cli_ok else "error",
            message=cli_version or cli_err or "可用",
            detail=str(settings.ltx_executable) if settings.ltx_executable else None,
        )
    )
    if not cli_ok:
        report.blocking_reasons.append(cli_err or "推理 CLI 不可用")

    # ---- 模型 ----
    model = model_service.effective_model()
    report.model_configured = model.configured
    report.model_path = str(model.path) if model.path else None
    report.model_error = None if model.status == "ok" else model.message
    checks.append(
        CheckItem(
            key="model",
            label="模型路径",
            status=model.status,
            message=model.message,
            detail=str(model.path) if model.path else None,
        )
    )
    if model.status == "error":
        report.blocking_reasons.append(model.message)

    # ---- FFmpeg ----
    ffmpeg_ok, ffmpeg_detail = check_ffmpeg()
    report.ffmpeg_available = ffmpeg_ok
    report.ffmpeg_error = None if ffmpeg_ok else ffmpeg_detail
    checks.append(
        CheckItem(
            key="ffmpeg",
            label="FFmpeg",
            status="ok" if ffmpeg_ok else "error",
            message=ffmpeg_detail or "可用",
        )
    )
    if not ffmpeg_ok:
        report.blocking_reasons.append(ffmpeg_detail or "FFmpeg 不可用")

    # ---- 目录可写 ----
    for key, label, path in (
        ("uploads", "上传目录", settings.uploads),
        ("outputs", "输出目录", settings.outputs),
        ("logs", "日志目录", settings.logs),
    ):
        writable, err = check_writable(path)
        checks.append(
            CheckItem(
                key=key,
                label=label,
                status="ok" if writable else "error",
                message=str(path) if writable else (err or "不可写"),
            )
        )
        if not writable:
            report.blocking_reasons.append(err or f"{label}不可写")

    # ---- 磁盘 ----
    total_gb, free_gb = disk_usage(settings.outputs)
    report.disk_total_gb = total_gb
    report.disk_free_gb = free_gb
    disk_status = "ok"
    disk_message = f"剩余 {free_gb} GiB / 共 {total_gb} GiB"
    if free_gb is not None and free_gb < settings.min_free_disk_gb:
        disk_status = "error"
        disk_message = f"磁盘剩余空间不足：{free_gb} GiB（需 ≥ {settings.min_free_disk_gb} GiB）"
        report.blocking_reasons.append(disk_message)
    elif free_gb is not None and free_gb < settings.min_free_disk_gb * 5:
        disk_status = "warn"
    checks.append(
        CheckItem(key="disk", label="剩余磁盘", status=disk_status, message=disk_message)
    )

    # ---- 内存（警告级）----
    total_mem, avail_mem = memory_info()
    report.total_memory_gb = total_mem
    report.available_memory_gb = avail_mem
    if total_mem is not None:
        mem_status = "ok"
        mem_message = f"共 {total_mem} GiB"
        if avail_mem is not None:
            mem_message += f"，当前可用约 {avail_mem} GiB"
            if avail_mem < settings.warn_free_memory_gb:
                mem_status = "warn"
                mem_message += "（内存偏低，建议降低分辨率/帧数）"
        checks.append(
            CheckItem(key="memory", label="统一内存", status=mem_status, message=mem_message)
        )

    return report
