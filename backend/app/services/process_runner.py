"""进程管理：以 asyncio 子进程运行 CLI，持续落盘日志，支持取消。"""

from __future__ import annotations

import asyncio
import logging
import os
import signal
import time
from collections.abc import Callable
from dataclasses import dataclass, field
from pathlib import Path

from app.core.config import Settings
from app.core.logging import redact
from app.utils.validators import gb_from_bytes

logger = logging.getLogger(__name__)

# 单次读取上限，避免超长行撑爆内存
_READ_CHUNK = 64 * 1024
_TAIL_FLUSH_INTERVAL = 0.5


@dataclass
class RunResult:
    exit_code: int | None
    canceled: bool
    timed_out: bool
    duration: float
    error: str | None = None
    tail: list[str] = field(default_factory=list)


def build_env(settings: Settings) -> dict[str, str]:
    """构造子进程环境：基于当前进程环境 + 离线变量，移除令牌。"""
    env = os.environ.copy()
    if settings.hf_hub_offline:
        env["HF_HUB_OFFLINE"] = "1"
    if settings.transformers_offline:
        env["TRANSFORMERS_OFFLINE"] = "1"
    env["PYTHONUNBUFFERED"] = "1"
    env["PYTHONIOENCODING"] = "utf-8"

    # 不把模型仓库 ID 当成路径；把模型 ID 保留给 CLI 自行解析是危险的，
    # 因此显式清掉可能干扰的参数环境变量。
    for key in (
        "HF_TOKEN",
        "HUGGINGFACE_TOKEN",
        "HF_HUB_TOKEN",
        "LTX_MODEL",
        "LTX_MODEL_ID",
    ):
        env.pop(key, None)
    return env


def memory_guard(settings: Settings) -> tuple[bool, str | None]:
    """返回 (是否允许启动, 警告信息)。"""
    from app.services.environment_service import memory_info

    _, available = memory_info()
    if available is None:
        return True, None
    if available < settings.min_free_memory_gb:
        return (
            False,
            f"可用内存不足（约 {available} GiB，低于阈值 {settings.min_free_memory_gb} GiB），"
            "请关闭其他占用内存的应用后重试",
        )
    if available < settings.warn_free_memory_gb:
        return True, f"可用内存偏低（约 {available} GiB），生成过程可能被系统终止"
    return True, None


def disk_guard(settings: Settings, path: Path) -> tuple[bool, str | None]:
    import shutil

    try:
        path.mkdir(parents=True, exist_ok=True)
        usage = shutil.disk_usage(path)
    except OSError as exc:
        return False, f"无法检查输出目录磁盘空间：{exc}"
    free_gb = gb_from_bytes(usage.free)
    if free_gb < settings.min_free_disk_gb:
        return (
            False,
            f"输出磁盘剩余空间不足：{free_gb} GiB（需 ≥ {settings.min_free_disk_gb} GiB）",
        )
    return True, None


class ProcessRunner:
    """单次 CLI 运行器（一个实例对应一个任务）。"""

    def __init__(
        self,
        *,
        cmd: list[str],
        cwd: Path | None,
        env: dict[str, str],
        log_file: Path,
        settings: Settings,
    ) -> None:
        self.cmd = cmd
        self.cwd = str(cwd) if cwd else None
        self.env = env
        self.log_file = log_file
        self.settings = settings

        self.process: asyncio.subprocess.Process | None = None
        self.pid: int | None = None
        self.cancel_requested = False
        self._tail: list[str] = []
        self._tail_lines = 200
        self._pump: asyncio.Task | None = None
        self.on_started: Callable[[int], None] | None = None

    @property
    def is_running(self) -> bool:
        return self.process is not None and self.process.returncode is None

    async def run(self) -> RunResult:
        started = time.monotonic()
        self.log_file.parent.mkdir(parents=True, exist_ok=True)

        with self.log_file.open("a", encoding="utf-8") as log_handle:
            header = (
                "===== LTX Studio task start "
                f"{time.strftime('%Y-%m-%d %H:%M:%S')} =====\n"
            )
            log_handle.write(header)
            log_handle.flush()

            try:
                self.process = await asyncio.create_subprocess_exec(
                    *self.cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.STDOUT,
                    cwd=self.cwd,
                    env=self.env,
                    start_new_session=True,  # 独立进程组，便于整组结束
                )
            except (OSError, ValueError) as exc:
                message = f"启动推理进程失败：{exc}"
                log_handle.write(f"[studio] {message}\n")
                log_handle.flush()
                self._tail.append(message)
                return RunResult(
                    exit_code=None,
                    canceled=False,
                    timed_out=False,
                    duration=time.monotonic() - started,
                    error=message,
                    tail=list(self._tail),
                )

            self.pid = self.process.pid
            log_handle.write(f"[studio] pid={self.pid}\n")
            log_handle.flush()
            if self.on_started is not None and self.pid is not None:
                try:
                    self.on_started(self.pid)
                except Exception:  # pragma: no cover - 回调失败不影响推理
                    logger.exception("记录 PID 回调失败")

            timed_out = False
            try:
                await asyncio.wait_for(
                    self._pump_output(log_handle),
                    timeout=self.settings.generation_timeout_seconds,
                )
            except asyncio.TimeoutError:
                timed_out = True
                log_handle.write(
                    f"[studio] 任务超过 {self.settings.generation_timeout_seconds} 秒，终止进程\n"
                )
                log_handle.flush()
                await self._terminate_group()
            except asyncio.CancelledError:
                self.cancel_requested = True
                await self._terminate_group()
                raise

            exit_code = None
            try:
                exit_code = await asyncio.wait_for(self.process.wait(), timeout=30)
            except asyncio.TimeoutError:
                await self._kill_group()
                try:
                    exit_code = await asyncio.wait_for(self.process.wait(), timeout=10)
                except asyncio.TimeoutError:
                    exit_code = None

            duration = time.monotonic() - started
            log_handle.write(
                f"[studio] process exited code={exit_code} "
                f"duration={duration:.1f}s canceled={self.cancel_requested} "
                f"timeout={timed_out}\n"
            )
            log_handle.write("===== LTX Studio task end =====\n")
            log_handle.flush()

        error = None
        if timed_out:
            error = f"任务执行超时（>{self.settings.generation_timeout_seconds}s），已终止进程"
        elif self.cancel_requested:
            error = "任务已被取消"
        elif exit_code != 0:
            error = f"推理进程退出码 {exit_code}"

        return RunResult(
            exit_code=exit_code,
            canceled=self.cancel_requested,
            timed_out=timed_out,
            duration=round(duration, 2),
            error=error,
            tail=list(self._tail),
        )

    async def _pump_output(self, log_handle) -> None:
        """持续读取 stdout，防止管道写满；同时保留尾部缓冲。"""
        assert self.process and self.process.stdout
        stream = self.process.stdout
        while True:
            chunk = await stream.read(_READ_CHUNK)
            if not chunk:
                break
            text = chunk.decode("utf-8", errors="replace")
            log_handle.write(redact(text))
            log_handle.flush()
            for line in text.splitlines():
                self._append_tail(line)

    def _append_tail(self, line: str) -> None:
        self._tail.append(line)
        if len(self._tail) > self._tail_lines * 2:
            self._tail = self._tail[-self._tail_lines :]

    @property
    def tail(self) -> list[str]:
        return self._tail[-self._tail_lines :]

    async def cancel(self) -> None:
        """请求取消：先 SIGTERM 进程组，宽限期后 SIGKILL。"""
        self.cancel_requested = True
        if not self.is_running:
            return
        await self._terminate_group()

    async def _terminate_group(self) -> None:
        if not self.is_running or self.pid is None:
            return
        self._signal_group(signal.SIGTERM)
        try:
            await asyncio.wait_for(
                self.process.wait(), timeout=self.settings.cancel_grace_seconds
            )
        except asyncio.TimeoutError:
            await self._kill_group()

    async def _kill_group(self) -> None:
        if self.pid is None:
            return
        self._signal_group(signal.SIGKILL)

    def _signal_group(self, sig: int) -> None:
        if self.pid is None:
            return
        try:
            os.killpg(os.getpgid(self.pid), sig)
        except ProcessLookupError:
            pass
        except OSError:
            # 进程组已不存在时退化为单进程信号
            try:
                os.kill(self.pid, sig)
            except OSError:
                pass
