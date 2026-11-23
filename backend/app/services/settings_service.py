"""运行期设置的读取（数据库白名单值覆盖默认配置）。"""

from __future__ import annotations

import logging

from app.core.config import settings
from app.db.database import session_scope
from app.db.repositories import SettingRepository

logger = logging.getLogger(__name__)

DEFAULTS = {
    "default_width": lambda: settings.default_width,
    "default_height": lambda: settings.default_height,
    "default_frames": lambda: settings.default_frames,
    "default_frame_rate": lambda: settings.default_frame_rate,
}


def stored() -> dict[str, str]:
    try:
        with session_scope() as session:
            return SettingRepository(session).get_all()
    except Exception as exc:  # pragma: no cover
        logger.warning("读取设置失败：%s", exc)
        return {}


def effective_low_ram() -> bool:
    raw = stored().get("low_ram")
    if raw is None:
        return settings.ltx_low_ram
    return raw.strip().lower() in {"true", "1", "yes"}


def effective_defaults() -> dict[str, int]:
    data = stored()
    result: dict[str, int] = {}
    for key, fallback in DEFAULTS.items():
        raw = data.get(key)
        try:
            result[key] = int(raw) if raw is not None else int(fallback())
        except ValueError:
            result[key] = int(fallback())
    return result
