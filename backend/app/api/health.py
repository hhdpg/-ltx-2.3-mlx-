"""健康检查与系统信息接口。"""

from __future__ import annotations

import platform
import sys

from fastapi import APIRouter

from app.core.config import settings
from app.schemas.system import HealthResponse, SystemInfoResponse
from app.services import model_service
from app.services.environment_service import collect_environment
from app.services.task_queue import queue_manager

router = APIRouter(tags=["system"])


@router.get("/health", response_model=HealthResponse)
def health(force: bool = False) -> HealthResponse:
    report = collect_environment(force=force)
    model = model_service.effective_model()

    return HealthResponse(
        status="ok" if report.ready else "degraded",
        app=settings.app_name,
        python=platform.python_version(),
        architecture=platform.machine(),
        mlx_available=report.mlx_available,
        mlx_device=report.mlx_device,
        mlx_error=report.mlx_error,
        cli_available=report.cli_available,
        cli_error=report.cli_error,
        model_configured=model.status != "error",
        model_path=report.model_path,
        model_error=report.model_error,
        ffmpeg_available=report.ffmpeg_available,
        ffmpeg_error=report.ffmpeg_error,
        queue_running=queue_manager.is_running,
        queue_size=queue_manager.pending,
        max_queue_size=settings.max_queue_size,
        offline_mode=settings.hf_hub_offline or settings.transformers_offline,
        ready=report.ready,
        blocking_reasons=report.blocking_reasons,
    )


@router.get("/system/info", response_model=SystemInfoResponse)
def system_info(force: bool = False) -> SystemInfoResponse:
    report = collect_environment(force=force)
    return SystemInfoResponse(
        app=settings.app_name,
        app_env=settings.app_env,
        python_version=sys.version.split()[0],
        platform=platform.platform(),
        architecture=platform.machine(),
        cpu_count=__import__("os").cpu_count(),
        total_memory_gb=report.total_memory_gb,
        available_memory_gb=report.available_memory_gb,
        disk_total_gb=report.disk_total_gb,
        disk_free_gb=report.disk_free_gb,
        model_id=settings.ltx_model_id,
        model_path=report.model_path,
        output_dir=str(settings.outputs),
        upload_dir=str(settings.uploads),
        log_dir=str(settings.logs),
        cli_path=str(settings.ltx_executable) if settings.ltx_executable else None,
        cli_version=report.cli_version,
        checks=report.checks,
        ready=report.ready,
        blocking_reasons=report.blocking_reasons,
    )
