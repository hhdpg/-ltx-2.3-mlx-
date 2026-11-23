"""MLX 环境检测：在推理虚拟环境内导入 mlx.core，不加载模型权重。"""

from __future__ import annotations

import json
import subprocess
from dataclasses import dataclass
from pathlib import Path

from app.core.config import settings

MLX_PROBE = (
    "import json\n"
    "try:\n"
    "    import mlx.core as mx\n"
    "    dev = str(mx.default_device())\n"
    "    print(json.dumps({'ok': True, 'device': dev}))\n"
    "except Exception as exc:\n"
    "    print(json.dumps({'ok': False, 'error': f'{type(exc).__name__}: {exc}'}))\n"
)


@dataclass
class MlxCheckResult:
    available: bool
    device: str | None
    error: str | None
    python_path: str | None


def detect_mlx(timeout: float = 60.0) -> MlxCheckResult:
    python = settings.ltx_python
    if not python or not python.is_file():
        return MlxCheckResult(
            available=False,
            device=None,
            error=f"推理虚拟环境 Python 不存在：{python or '未配置 LTX_PYTHON'}",
            python_path=str(python) if python else None,
        )

    try:
        proc = subprocess.run(  # noqa: S603 - 固定脚本，无 shell
            [str(python), "-c", MLX_PROBE],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_probe_env(),
            cwd=str(settings.ltx_project_root) if settings.ltx_project_root else None,
        )
    except subprocess.TimeoutExpired:
        return MlxCheckResult(
            available=False,
            device=None,
            error=f"MLX 检测超时（>{timeout:.0f}s）",
            python_path=str(python),
        )
    except OSError as exc:
        return MlxCheckResult(
            available=False,
            device=None,
            error=f"无法执行推理环境 Python：{exc}",
            python_path=str(python),
        )

    payload = _parse_payload(proc.stdout)
    if payload is None:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else "无输出"
        return MlxCheckResult(
            available=False,
            device=None,
            error=f"MLX 检测失败（退出码 {proc.returncode}）：{tail}",
            python_path=str(python),
        )

    if payload.get("ok"):
        device = payload.get("device")
        is_gpu = bool(device and "gpu" in device.lower())
        return MlxCheckResult(
            available=is_gpu,
            device=device,
            error=None if is_gpu else f"MLX 默认设备不是 GPU：{device}",
            python_path=str(python),
        )

    return MlxCheckResult(
        available=False,
        device=None,
        error=payload.get("error") or "MLX 不可用",
        python_path=str(python),
    )


def _parse_payload(stdout: str) -> dict | None:
    for line in reversed((stdout or "").strip().splitlines()):
        line = line.strip()
        if line.startswith("{"):
            try:
                return json.loads(line)
            except json.JSONDecodeError:
                continue
    return None


def _probe_env() -> dict[str, str]:
    import os

    env = os.environ.copy()
    if settings.hf_hub_offline:
        env["HF_HUB_OFFLINE"] = "1"
    if settings.transformers_offline:
        env["TRANSFORMERS_OFFLINE"] = "1"
    # 清除可能存在的令牌，避免进入日志
    for key in ("HF_TOKEN", "HUGGINGFACE_TOKEN", "HF_HUB_TOKEN"):
        env.pop(key, None)
    return env


def cli_help_check(timeout: float = 120.0) -> tuple[bool, str | None, str | None]:
    """执行 ltx-2-mlx --help，返回 (可用, 错误, 版本行)。"""
    exe: Path | None = settings.ltx_executable
    if not exe:
        return False, "未配置 LTX_EXECUTABLE", None
    if not exe.is_file():
        return False, f"CLI 不存在：{exe}", None
    if not (exe.stat().st_mode & 0o111):
        return False, f"CLI 没有可执行权限：{exe}", None

    try:
        proc = subprocess.run(  # noqa: S603
            [str(exe), "--help"],
            capture_output=True,
            text=True,
            timeout=timeout,
            env=_probe_env(),
            cwd=str(settings.ltx_project_root) if settings.ltx_project_root else None,
        )
    except subprocess.TimeoutExpired:
        return False, f"ltx-2-mlx --help 超时（>{timeout:.0f}s）", None
    except OSError as exc:
        return False, f"无法执行 ltx-2-mlx：{exc}", None

    output = (proc.stdout or "") + (proc.stderr or "")
    if proc.returncode != 0:
        tail = output.strip().splitlines()
        message = tail[0] if tail else "无输出"
        return False, f"ltx-2-mlx --help 退出码 {proc.returncode}：{message}", None

    return True, None, _extract_version(output)


def _extract_version(output: str) -> str | None:
    for line in output.splitlines():
        lowered = line.lower()
        if "version" in lowered and any(ch.isdigit() for ch in line):
            return line.strip()[:200]
    return None
