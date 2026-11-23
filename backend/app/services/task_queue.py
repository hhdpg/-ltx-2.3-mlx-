"""单任务队列：严格串行，同一时刻最多一个推理进程。"""

from __future__ import annotations

import asyncio
import logging
from pathlib import Path

from app.core.config import settings
from app.db.database import session_scope
from app.db.models import TaskStatus
from app.db.repositories import TaskRepository
from app.services import file_service
from app.services.process_runner import ProcessRunner

logger = logging.getLogger(__name__)


class TaskQueueManager:
    def __init__(self) -> None:
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker: asyncio.Task | None = None
        self._runners: dict[str, ProcessRunner] = {}
        self._enqueued: set[str] = set()
        self._current_task_id: str | None = None
        self._stopping = False
        self._lock = asyncio.Lock()

    # ---- 生命周期 ----
    async def start(self) -> None:
        if self._worker and not self._worker.done():
            return
        self._stopping = False
        await self._recover()
        self._worker = asyncio.create_task(self._run_worker(), name="ltx-task-worker")
        logger.info("任务队列 worker 已启动")

    async def stop(self) -> None:
        self._stopping = True
        runner = self._runners.get(self._current_task_id) if self._current_task_id else None
        if runner is not None:
            await runner.cancel()
        if self._worker:
            self._worker.cancel()
            try:
                await self._worker
            except asyncio.CancelledError:
                pass
            self._worker = None
        logger.info("任务队列 worker 已停止")

    async def _recover(self) -> None:
        """启动恢复：残留活动任务标记失败，QUEUED 任务重新入队。"""
        with session_scope() as session:
            repo = TaskRepository(session)
            failed = repo.fail_interrupted()
            queued = repo.queued_tasks_ordered()
            queued_ids = [task.id for task in queued]
        if failed:
            logger.warning("已将 %d 个残留任务标记为失败", len(failed))
        for task_id in queued_ids:
            self.enqueue_existing(task_id)
        if queued_ids:
            logger.info("已重新入队 %d 个未执行任务", len(queued_ids))

    # ---- 入队 ----
    def enqueue_existing(self, task_id: str) -> bool:
        """幂等入队。返回是否真的加入。"""
        if task_id in self._enqueued:
            return False
        self._enqueued.add(task_id)
        self._queue.put_nowait(task_id)
        return True

    async def submit(self, task_id: str) -> None:
        await self._lock.acquire()
        try:
            self._enqueued.add(task_id)
            self._queue.put_nowait(task_id)
        finally:
            self._lock.release()

    # ---- 状态 ----
    @property
    def is_running(self) -> bool:
        return self._current_task_id is not None

    @property
    def current_task_id(self) -> str | None:
        return self._current_task_id

    @property
    def pending(self) -> int:
        return self._queue.qsize()

    def queued_count(self) -> int:
        with session_scope() as session:
            return TaskRepository(session).count_queued()

    def register_runner(self, task_id: str, runner: ProcessRunner) -> None:
        self._runners[task_id] = runner

    def record_pid(self, task_id: str, pid: int | None) -> None:
        """进程启动后回写 PID，便于排查残留进程。"""
        if pid is None:
            return
        with session_scope() as session:
            repo = TaskRepository(session)
            task = repo.get(task_id)
            if task is not None and task.pid != pid:
                task.pid = pid
                repo.save(task)

    def unregister_runner(self, task_id: str) -> None:
        self._runners.pop(task_id, None)

    # ---- worker ----
    async def _run_worker(self) -> None:
        while not self._stopping:
            try:
                task_id = await self._queue.get()
            except asyncio.CancelledError:
                raise

            self._enqueued.discard(task_id)
            self._current_task_id = task_id
            try:
                await self._process(task_id)
            except asyncio.CancelledError:
                raise
            except Exception:  # pragma: no cover - 保证 worker 不死
                logger.exception("处理任务 %s 时发生未捕获异常", task_id)
            finally:
                self._current_task_id = None
                self._queue.task_done()

    async def _process(self, task_id: str) -> None:
        from app.services import generation_service

        with session_scope() as session:
            task = TaskRepository(session).get(task_id)
            if task is None:
                logger.warning("队列中的任务 %s 已不存在", task_id)
                return
            status = task.status

        if status == TaskStatus.CANCELED.value:
            logger.info("任务 %s 已取消，跳过", task_id)
            return
        if status in (
            TaskStatus.SUCCEEDED.value,
            TaskStatus.FAILED.value,
        ):
            logger.info("任务 %s 已结束（%s），跳过", task_id, status)
            return

        await generation_service.execute_task(self, task_id)

    # ---- 取消 ----
    async def cancel(self, task_id: str) -> tuple[bool, str]:
        """取消排队/运行中的任务，返回 (成功, 说明)。"""
        with session_scope() as session:
            repo = TaskRepository(session)
            task = repo.get(task_id)
            if task is None:
                return False, "任务不存在"
            status = task.status
            if status == TaskStatus.QUEUED.value:
                repo.mark_canceled(task)
                canceled_queued = True
            elif status in (TaskStatus.STARTING.value, TaskStatus.RUNNING.value):
                repo.mark_cancel_requested(task)
                canceled_queued = False
            elif status == TaskStatus.CANCELING.value:
                return True, "任务正在取消"
            else:
                return False, f"当前状态（{status}）不可取消"

        if canceled_queued:
            logger.info("排队任务已取消 id=%s", task_id)
            return True, "排队任务已取消"

        runner = self._runners.get(task_id)
        if runner is not None:
            await runner.cancel()
            return True, "已发送取消信号"
        # 进程尚未启动：把状态落为已取消
        with session_scope() as session:
            repo = TaskRepository(session)
            task = repo.get(task_id)
            if task is not None and task.status in (
                TaskStatus.CANCELING.value,
                TaskStatus.STARTING.value,
            ):
                repo.mark_canceled(task)
        return True, "任务已取消"

    # ---- 清理 ----
    def delete_task_files(
        self, task_id: str, output_path: str | None, log_path: str | None
    ) -> bool:
        """删除输出与日志文件（任务记录由调用方删除）。"""
        deleted = False
        if output_path:
            deleted = file_service.delete_file(Path(output_path)) or deleted
        if log_path:
            file_service.delete_file(Path(log_path))
        return deleted


queue_manager = TaskQueueManager()
