"""生成服务：创建任务、准备命令、执行并回写状态。"""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path
from typing import TYPE_CHECKING

from app.core.config import settings
from app.core.paths import safe_join
from app.db.database import session_scope
from app.db.models import GenerationTask, TaskStatus, TaskType
from app.db.repositories import TaskRepository
from app.schemas.generation import GenerationParams
from app.services import file_service, model_service, settings_service, video_service
from app.services.process_runner import (
    ProcessRunner,
    build_env,
    disk_guard,
    memory_guard,
)
from app.utils.command_builder import (
    CommandBuildError,
    build_command,
    build_extend_command,
    build_retake_command,
    describe_command,
)

if TYPE_CHECKING:  # pragma: no cover
    from app.services.task_queue import TaskQueueManager

logger = logging.getLogger(__name__)


class GenerationError(RuntimeError):
    """提交或执行前置条件不满足。"""

    def __init__(self, message: str, code: str = "unavailable") -> None:
        super().__init__(message)
        self.code = code


def create_task(
    params: GenerationParams,
    *,
    image_path: Path | None,
    model_path: Path,
    queue_depth: int,
    project_id: str | None = None,
) -> GenerationTask:
    """创建 QUEUED 任务记录。"""
    if queue_depth >= settings.max_queue_size:
        raise GenerationError(
            f"队列已满（最多 {settings.max_queue_size} 个等待任务），请稍后再试",
            code="queue_full",
        )

    task_id = str(uuid.uuid4())
    output_file = safe_join(settings.outputs, f"{task_id}.mp4")
    log_file = safe_join(settings.task_log_dir, f"{task_id}.log")

    task = GenerationTask(
        id=task_id,
        task_type=params.task_type,
        prompt=params.prompt,
        image_path=str(image_path) if image_path else None,
        model_path=str(model_path),
        mode=params.mode,
        width=params.width,
        height=params.height,
        frames=params.frames,
        frame_rate=params.frame_rate,
        seed=params.seed,
        status=TaskStatus.QUEUED.value,
        output_path=str(output_file),
        log_path=str(log_file),
        project_id=project_id,
    )

    with session_scope() as session:
        TaskRepository(session).add(task)
        session.expunge(task)

    logger.info(
        "任务已创建 id=%s type=%s size=%sx%s frames=%s",
        task.id,
        task.task_type,
        task.width,
        task.height,
        task.frames,
    )
    return task


def create_extend_task(
    *,
    project_id: str,
    source_segment_id: str,
    action_prompt: str,
    final_prompt: str,
    extend_frames: int,
    source_video_path: Path,
    model_path: Path,
    source_info: video_service.VideoInfo,
    seed: int | None,
    anchor_image_path: Path | None,
    anchor_frame: int | None,
    anchor_strength: float | None,
    queue_depth: int,
) -> GenerationTask:
    """创建 EXTEND 任务（输出到项目专属目录，绝不覆盖源视频）。"""
    from app.services import project_service

    if queue_depth >= settings.max_queue_size:
        raise GenerationError(
            f"队列已满（最多 {settings.max_queue_size} 个等待任务），请稍后再试",
            code="queue_full",
        )

    task_id = str(uuid.uuid4())
    output_file = project_service.segment_output_path(project_id, task_id)
    if output_file.resolve() == source_video_path.resolve():
        raise GenerationError("输出路径不得与源视频相同", code="path_conflict")

    log_file = safe_join(settings.task_log_dir, f"{task_id}.log")

    task = GenerationTask(
        id=task_id,
        task_type=TaskType.EXTEND.value,
        prompt=action_prompt,
        final_prompt=final_prompt,
        image_path=None,
        model_path=str(model_path),
        mode="distilled",
        # Extend 不传尺寸/帧率给 CLI，这里记录源视频信息便于展示
        width=source_info.width,
        height=source_info.height,
        frames=(source_info.frame_count or 0) + extend_frames * 8,
        frame_rate=int(round(source_info.frame_rate)),
        seed=seed,
        status=TaskStatus.QUEUED.value,
        output_path=str(output_file),
        log_path=str(log_file),
        project_id=project_id,
        source_segment_id=source_segment_id,
        extend_frames=extend_frames,
        source_video_path=str(source_video_path),
        anchor_image_path=str(anchor_image_path) if anchor_image_path else None,
        anchor_frame=anchor_frame,
        anchor_strength=anchor_strength,
    )

    with session_scope() as session:
        TaskRepository(session).add(task)
        session.expunge(task)

    logger.info(
        "续写任务已创建 id=%s project=%s source=%s extend_frames=%s",
        task.id,
        project_id,
        source_segment_id,
        extend_frames,
    )
    return task


def create_retake_task(
    *,
    prompt: str,
    final_prompt: str,
    source_video_path: Path,
    retake_start: int,
    retake_end: int,
    keep_audio: bool,
    model_path: Path,
    source_info: video_service.VideoInfo,
    seed: int | None,
    project_id: str | None = None,
    source_segment_id: str | None = None,
    output_file: Path | None = None,
    queue_depth: int,
) -> GenerationTask:
    """创建 RETAKE 任务。

    单条任务与连续任务共用：project_id 为空即"单条"改写，否则结果会
    作为该项目的版本（先尝试创建，失败不影响任务本身）。
    """
    if queue_depth >= settings.max_queue_size:
        raise GenerationError(
            f"队列已满（最多 {settings.max_queue_size} 个等待任务），请稍后再试",
            code="queue_full",
        )

    task_id = str(uuid.uuid4())
    if output_file is None:
        if project_id:
            from app.services import project_service

            output_file = project_service.segment_output_path(project_id, task_id)
        else:
            output_file = safe_join(settings.outputs, f"{task_id}.mp4")
    if output_file.resolve() == source_video_path.resolve():
        raise GenerationError("输出路径不得与源视频相同", code="path_conflict")

    log_file = safe_join(settings.task_log_dir, f"{task_id}.log")

    task = GenerationTask(
        id=task_id,
        task_type=TaskType.RETAKE.value,
        prompt=prompt,
        final_prompt=final_prompt,
        image_path=None,
        model_path=str(model_path),
        mode="distilled",
        width=source_info.width,
        height=source_info.height,
        frames=source_info.frame_count or 0,
        frame_rate=int(round(source_info.frame_rate)),
        seed=seed,
        status=TaskStatus.QUEUED.value,
        output_path=str(output_file),
        log_path=str(log_file),
        project_id=project_id,
        source_segment_id=source_segment_id,
        source_video_path=str(source_video_path),
        retake_start=retake_start,
        retake_end=retake_end,
        keep_audio=keep_audio,
    )

    with session_scope() as session:
        TaskRepository(session).add(task)
        session.expunge(task)

    logger.info(
        "局部重拍任务已创建 id=%s range=[%s, %s) project=%s",
        task.id,
        retake_start,
        retake_end,
        project_id or "-",
    )
    return task


def preflight(task: GenerationTask) -> tuple[bool, str]:
    """启动前检查：模型、CLI、磁盘、内存、输入图片。"""
    model_ok, model_error, model_path = model_service.model_usable()
    if not model_ok:
        return False, model_error or "模型不可配置"
    if model_path is None:
        return False, "模型路径无效"

    if not settings.cli_available:
        return False, f"推理 CLI 不可用：{settings.ltx_executable or '未配置 LTX_EXECUTABLE'}"

    disk_ok, disk_error = disk_guard(settings, settings.outputs)
    if not disk_ok:
        return False, disk_error or "磁盘空间不足"

    if task.task_type == TaskType.I2V.value:
        if not task.image_path:
            return False, "I2V 任务缺少输入图片"
        image = Path(task.image_path)
        if not image.is_file():
            return False, f"输入图片不存在：{image}"

    if task.task_type == TaskType.EXTEND.value:
        if not task.source_video_path:
            return False, "续写任务缺少源视频"
        source = file_service.resolve_allowed(task.source_video_path, "outputs")
        if source is None:
            return False, "源视频不存在或不在允许目录内"
        try:
            video_service.probe_video(source, validate_size=True)
        except video_service.VideoError as exc:
            return False, f"源视频校验失败：{exc}"

    if task.task_type == TaskType.RETAKE.value:
        if not task.source_video_path:
            return False, "局部重拍任务缺少源视频"
        source = file_service.resolve_allowed(task.source_video_path, "outputs")
        if source is None:
            return False, "源视频不存在或不在允许目录内"
        try:
            info = video_service.probe_video(source)
            video_service.validate_retake_range(
                info,
                task.retake_start or 0,
                task.retake_end or 0,
            )
        except video_service.VideoError as exc:
            return False, f"源视频校验失败：{exc}"

    mem_ok, mem_message = memory_guard(settings)
    if not mem_ok:
        return False, mem_message or "可用内存不足"
    if mem_message:
        logger.warning("任务 %s 内存提示：%s", task.id, mem_message)

    return True, ""


async def execute_task(manager: "TaskQueueManager", task_id: str) -> None:
    """在 worker 中执行单个任务并回写状态。"""
    with session_scope() as session:
        repo = TaskRepository(session)
        task = repo.get(task_id)
        if task is None:
            logger.warning("任务 %s 不存在，跳过", task_id)
            return
        if task.status != TaskStatus.QUEUED.value:
            logger.info("任务 %s 状态为 %s，跳过执行", task_id, task.status)
            return
        repo.mark_started(task)
        repo.mark_running(task)
        session.expunge(task)

    ok, message = preflight(task)
    if not ok:
        _fail(task_id, message, None)
        return

    model_ok, _, model_path = model_service.model_usable()
    if not model_ok or model_path is None:
        _fail(task_id, "模型不可用", None)
        return

    output_path = task.output_path or str(safe_join(settings.outputs, f"{task.id}.mp4"))
    Path(output_path).parent.mkdir(parents=True, exist_ok=True)
    log_path = Path(task.log_path or safe_join(settings.task_log_dir, f"{task.id}.log"))

    try:
        if task.is_extend:
            cmd = build_extend_command(
                task,
                settings,
                output_path=output_path,
                model_path=str(model_path),
                low_ram=settings_service.effective_low_ram(),
            )
        elif task.is_retake:
            cmd = build_retake_command(
                task,
                settings,
                output_path=output_path,
                model_path=str(model_path),
                low_ram=settings_service.effective_low_ram(),
            )
        else:
            cmd = build_command(
                task,
                settings,
                output_path=output_path,
                model_path=str(model_path),
                low_ram=settings_service.effective_low_ram(),
            )
    except CommandBuildError as exc:
        _fail(task_id, f"命令构造失败：{exc}", None)
        return

    runner = ProcessRunner(
        cmd=cmd,
        cwd=settings.ltx_project_root,
        env=build_env(settings),
        log_file=log_path,
        settings=settings,
    )
    runner.on_started = lambda pid: manager.record_pid(task_id, pid)
    manager.register_runner(task_id, runner)

    with log_path.open("a", encoding="utf-8") as handle:
        handle.write(f"[studio] command: {describe_command(cmd)}\n")
        handle.write(f"[studio] cwd: {settings.ltx_project_root}\n")
        handle.flush()

    started = time.monotonic()
    try:
        result = await runner.run()
    except Exception as exc:  # pragma: no cover - 防御性兜底
        logger.exception("任务 %s 执行异常", task_id)
        manager.unregister_runner(task_id)
        _fail(task_id, f"执行异常：{type(exc).__name__}: {exc}", None)
        return
    finally:
        manager.unregister_runner(task_id)

    elapsed = round(time.monotonic() - started, 2)

    if result.canceled:
        _mark_canceled(task_id, elapsed)
        return

    if result.timed_out:
        _fail(task_id, result.error or "任务执行超时", result.exit_code)
        return

    if result.exit_code != 0:
        summary = _summarize_failure(result.tail, result.exit_code)
        _fail(task_id, summary, result.exit_code)
        return

    ready, problem = file_service.output_ready(output_path)
    if not ready:
        _fail(task_id, problem or "输出文件校验失败", result.exit_code)
        return

    with session_scope() as session:
        repo = TaskRepository(session)
        task = repo.get(task_id)
        if task is None:
            return
        repo.mark_succeeded(task, output_path)

        if task.project_id:
            _attach_segment(session, task, output_path)

    logger.info("任务完成 id=%s 用时=%.1fs", task_id, elapsed)


def _attach_segment(session, task: GenerationTask, output_path: str) -> None:
    """任务成功后创建版本记录（失败不影响任务成功状态）。"""
    from app.services import project_service

    if task.segment_id:
        return  # 已创建（幂等）
    try:
        info = project_service.video_service.probe_video(Path(output_path))
        project_service.create_segment_from_task(
            session,
            task=task,
            project_id=task.project_id,
            parent_segment_id=task.source_segment_id,
            action_prompt=task.prompt,
            final_prompt=task.final_prompt or task.prompt,
            extend_frames=task.extend_frames,
            video_info=info,
        )
        session.flush()
        logger.info(
            "已创建版本记录 task=%s project=%s segment=%s",
            task.id,
            task.project_id,
            task.segment_id,
        )
    except Exception as exc:
        logger.exception("创建版本记录失败 task=%s：%s", task.id, exc)


def _summarize_failure(tail: list[str], exit_code: int | None) -> str:
    """从日志末尾提取简明错误摘要（不猜测成功）。"""
    interesting: list[str] = []
    for line in reversed(tail):
        stripped = line.strip()
        if not stripped:
            continue
        lowered = stripped.lower()
        if any(
            token in lowered
            for token in (
                "error",
                "exception",
                "traceback",
                "failed",
                "out of memory",
                "killed",
                "no such file",
            )
        ):
            interesting.append(stripped)
        if len(interesting) >= 3:
            break

    if interesting:
        head = interesting[0][:500]
        return f"推理失败（退出码 {exit_code}）：{head}"
    if exit_code is not None and exit_code < 0:
        if exit_code == -9:
            return "推理进程被系统终止（可能是内存不足），请降低分辨率或帧数"
        return f"推理进程异常终止（信号 {-exit_code}）"
    return f"推理失败（退出码 {exit_code}），请查看完整日志"


def _fail(task_id: str, message: str, exit_code: int | None) -> None:
    with session_scope() as session:
        repo = TaskRepository(session)
        task = repo.get(task_id)
        if task is None:
            return
        repo.mark_failed(task, message, exit_code)
    logger.warning("任务失败 id=%s：%s", task_id, message)


def _mark_canceled(task_id: str, elapsed: float) -> None:
    with session_scope() as session:
        repo = TaskRepository(session)
        task = repo.get(task_id)
        if task is None:
            return
        repo.mark_canceled(task)
    logger.info("任务已取消 id=%s 用时=%.1fs", task_id, elapsed)
