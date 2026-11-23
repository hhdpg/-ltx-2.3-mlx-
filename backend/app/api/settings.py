"""设置接口：只允许修改白名单配置，模型路径写库前重新校验。"""

from __future__ import annotations

import logging
from pathlib import Path

from fastapi import APIRouter, HTTPException, status

from app.core.config import settings
from app.db.database import session_scope
from app.db.repositories import SettingRepository
from app.schemas.system import SettingsResponse, SettingsUpdate
from app.services import environment_service, model_service
from app.utils.validators import (
    ValidationError,
    validate_frame_rate,
    validate_frames,
    validate_resolution,
)

logger = logging.getLogger(__name__)

router = APIRouter(tags=["settings"])

SETTING_KEYS = {
    "default_width",
    "default_height",
    "default_frames",
    "default_frame_rate",
    "low_ram",
}


def _read_stored() -> dict[str, str]:
    with session_scope() as session:
        return SettingRepository(session).get_all()


def _effective(stored: dict[str, str]) -> dict[str, int | bool]:
    return {
        "default_width": int(stored.get("default_width", settings.default_width)),
        "default_height": int(stored.get("default_height", settings.default_height)),
        "default_frames": int(stored.get("default_frames", settings.default_frames)),
        "default_frame_rate": int(
            stored.get("default_frame_rate", settings.default_frame_rate)
        ),
        "low_ram": stored.get("low_ram", str(settings.ltx_low_ram).lower())
        in {"true", "1", "yes"},
    }


def build_response() -> SettingsResponse:
    stored = _read_stored()
    effective = _effective(stored)
    model = model_service.effective_model()
    return SettingsResponse(
        default_width=int(effective["default_width"]),
        default_height=int(effective["default_height"]),
        default_frames=int(effective["default_frames"]),
        default_frame_rate=int(effective["default_frame_rate"]),
        low_ram=bool(effective["low_ram"]),
        model_id=settings.ltx_model_id,
        model_path=str(model.path) if model.path else None,
        output_dir=str(settings.outputs),
        upload_dir=str(settings.uploads),
        allowed_frames=list(settings.allowed_frames),
        allowed_frame_rates=list(settings.allowed_frame_rates),
        allowed_resolutions=[[w, h] for w, h in settings.allowed_resolutions],
        allowed_extend_frames=list(settings.allowed_extend_frames),
        default_extend_frames=settings.default_extend_frames,
        max_prompt_length=settings.max_prompt_length,
        max_upload_mb=settings.max_upload_mb,
        max_queue_size=settings.max_queue_size,
        offline_mode=settings.hf_hub_offline or settings.transformers_offline,
    )


@router.get("/settings", response_model=SettingsResponse)
def read_settings() -> SettingsResponse:
    return build_response()


@router.put("/settings", response_model=SettingsResponse)
def update_settings(payload: SettingsUpdate) -> SettingsResponse:
    updates: dict[str, str] = {}

    if payload.default_width is not None or payload.default_height is not None:
        current = _effective(_read_stored())
        width = payload.default_width or int(current["default_width"])
        height = payload.default_height or int(current["default_height"])
        try:
            validate_resolution(width, height)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        updates["default_width"] = str(width)
        updates["default_height"] = str(height)

    if payload.default_frames is not None:
        try:
            validate_frames(payload.default_frames)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        updates["default_frames"] = str(payload.default_frames)

    if payload.default_frame_rate is not None:
        try:
            validate_frame_rate(payload.default_frame_rate)
        except ValidationError as exc:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(exc)
            ) from exc
        updates["default_frame_rate"] = str(payload.default_frame_rate)

    if payload.low_ram is not None:
        updates["low_ram"] = "true" if payload.low_ram else "false"

    if payload.model_path is not None:
        raw = payload.model_path.strip()
        if raw:
            candidate = Path(raw).expanduser()
            check = model_service.check_model_path(candidate.resolve())
            if check.status == "error":
                raise HTTPException(
                    status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                    detail=f"模型目录校验失败：{check.message}",
                )
            model_service.save_model_path(str(candidate))
            environment_service.invalidate_cache()
            logger.info("模型路径已更新：%s", candidate)
        else:
            model_service.save_model_path(None)
            environment_service.invalidate_cache()
            logger.info("模型路径已清空，回退到环境变量或缓存")

    if updates:
        with session_scope() as session:
            repo = SettingRepository(session)
            for key, value in updates.items():
                if key in SETTING_KEYS:
                    repo.set(key, value)

    return build_response()
