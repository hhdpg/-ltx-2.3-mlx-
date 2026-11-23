"""统一日志：应用日志落盘 + 敏感信息脱敏。"""

from __future__ import annotations

import logging
import re
from logging.handlers import RotatingFileHandler
from pathlib import Path

from app.core.config import settings

_SENSITIVE_PAT = re.compile(
    r"(?i)\b(HF_TOKEN|HUGGINGFACE_TOKEN|HF_HUB_TOKEN|API_KEY|SECRET|PASSWORD|TOKEN)"
    r"\s*[=:]\s*\S+"
)
_HF_TOKEN_PAT = re.compile(r"\bhf_[A-Za-z0-9]{10,}\b")


def redact(text: str) -> str:
    """移除日志中可能出现的密钥形态字符串。"""
    if not text:
        return text
    cleaned = _SENSITIVE_PAT.sub(r"\1=***", text)
    return _HF_TOKEN_PAT.sub("hf_***", cleaned)


class RedactingFilter(logging.Filter):
    def filter(self, record: logging.LogRecord) -> bool:
        try:
            message = record.getMessage()
        except Exception:  # pragma: no cover - 格式化异常不应炸掉日志
            return True
        cleaned = redact(message)
        if cleaned != message:
            record.msg = cleaned
            record.args = ()
        return True


_CONFIGURED = False


def setup_logging(log_dir: Path | None = None) -> Path:
    """配置根日志，写入 logs/app.log，并返回日志文件路径。"""
    global _CONFIGURED
    target_dir = log_dir or settings.logs
    target_dir.mkdir(parents=True, exist_ok=True)
    log_file = target_dir / "app.log"

    root = logging.getLogger()
    if _CONFIGURED:
        return log_file

    root.setLevel(logging.INFO)
    formatter = logging.Formatter(
        "%(asctime)s | %(levelname)-8s | %(name)s | %(message)s",
        datefmt="%Y-%m-%d %H:%M:%S",
    )

    file_handler = RotatingFileHandler(
        log_file, maxBytes=10 * 1024 * 1024, backupCount=5, encoding="utf-8"
    )
    file_handler.setFormatter(formatter)
    file_handler.addFilter(RedactingFilter())

    console = logging.StreamHandler()
    console.setFormatter(formatter)
    console.addFilter(RedactingFilter())

    root.addHandler(file_handler)
    root.addHandler(console)

    # 降低第三方库噪音
    for noisy in ("httpx", "httpcore", "multipart", "watchfiles"):
        logging.getLogger(noisy).setLevel(logging.WARNING)

    _CONFIGURED = True
    return log_file


def get_logger(name: str) -> logging.Logger:
    return logging.getLogger(name)
