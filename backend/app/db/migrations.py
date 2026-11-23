"""SQLite 增量迁移：为 V1.1 连续续写补充字段与表。

设计原则：
  * 幂等 —— 重复启动不会重复执行
  * 只用 ALTER TABLE ADD COLUMN（SQLite 支持），不重建表
  * 迁移前自动备份数据库到 data/backups/
  * 任何一步失败都不影响服务启动（create_all 已保证新表存在）
"""

from __future__ import annotations

import logging
import shutil
from datetime import datetime
from pathlib import Path

from sqlalchemy import inspect, text
from sqlalchemy.engine import Engine

from app.core.config import settings

logger = logging.getLogger(__name__)

# generation_task 新增列：列名 -> SQLite 类型定义
TASK_NEW_COLUMNS: dict[str, str] = {
    "project_id": "VARCHAR(36)",
    "source_segment_id": "VARCHAR(36)",
    "extend_frames": "INTEGER",
    "source_video_path": "TEXT",
    "final_prompt": "TEXT",
    "anchor_image_path": "TEXT",
    "anchor_frame": "INTEGER",
    "anchor_strength": "FLOAT",
    "segment_id": "VARCHAR(36)",
    # V1.2 局部重拍
    "retake_start": "INTEGER",
    "retake_end": "INTEGER",
    "keep_audio": "BOOLEAN",
}


def _backup_database() -> Path | None:
    """迁移前备份 SQLite 文件；非 SQLite 或文件不存在时跳过。"""
    try:
        db_path = settings.db_path
    except ValueError:
        return None
    if not db_path.is_file():
        return None

    backup_dir = settings.data_dir / "backups"
    backup_dir.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    target = backup_dir / f"{db_path.stem}-{stamp}{db_path.suffix}"
    try:
        shutil.copy2(db_path, target)
    except OSError as exc:  # pragma: no cover
        logger.warning("数据库备份失败：%s", exc)
        return None
    logger.info("数据库已备份：%s", target)
    return target


def _columns(engine: Engine, table: str) -> set[str]:
    inspector = inspect(engine)
    if table not in inspector.get_table_names():
        return set()
    return {col["name"] for col in inspector.get_columns(table)}


def run_migrations(engine: Engine) -> list[str]:
    """执行增量迁移，返回已应用的变更列表。"""
    applied: list[str] = []

    existing = _columns(engine, "generation_task")
    if not existing:
        # 全新数据库：create_all 已建好完整表结构
        return applied

    pending = {
        name: ddl for name, ddl in TASK_NEW_COLUMNS.items() if name not in existing
    }
    if not pending:
        return applied

    _backup_database()

    with engine.begin() as conn:
        for name, ddl in pending.items():
            try:
                conn.execute(
                    text(f"ALTER TABLE generation_task ADD COLUMN {name} {ddl}")
                )
                applied.append(name)
                logger.info("迁移：generation_task 新增列 %s", name)
            except Exception as exc:  # pragma: no cover - 并发/重复执行时忽略
                logger.warning("迁移列 %s 失败（可能已存在）：%s", name, exc)

    if applied:
        with engine.begin() as conn:
            conn.execute(
                text(
                    "CREATE INDEX IF NOT EXISTS ix_generation_task_project_id "
                    "ON generation_task (project_id)"
                )
            )
    return applied
