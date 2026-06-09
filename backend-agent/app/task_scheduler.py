from __future__ import annotations

"""定时任务调度器模块。

实现周期性任务调度，包括 Bot 任务、记忆更新、数据库清理、
文档记忆提取和记忆自审查等任务的定时执行、并发控制和 LLM 槽位管理。
"""

import asyncio
import sqlite3
import threading
import traceback
from pathlib import Path
from uuid import uuid4

from app.bot_process_manager import BotProcessManager
from app.db.log_store import insert_project_log
from app.db.core import is_database_locked_error
from app.db.slot_store import (
    acquire_llm_slot,
    cleanup_stale_llm_slots,
    release_llm_slot,
    reset_all_llm_slots,
)
from app.yaml_config import get_yaml_config
from app.db.task_store import (
    claim_due_one_time_tasks,
    claim_due_periodic_tasks,
    mark_one_time_task_finished,
    mark_periodic_task_finished,
    reset_running_one_time_tasks,
    reset_running_periodic_tasks,
    unclaim_task,
    list_overdue_tasks,
    update_periodic_task,
    disable_periodic_task,
)
from app.db.settings_store import load_settings_from_database
from app.logger import get_logger
from app.task_runtime import (
    MEMORY_UPDATE_REVIEW_REQUIRED_PREFIX,
    ensure_task_runtime,
    run_database_cleanup_task,
    run_document_memory_extraction_task,
    run_explicit_memory_task,
    run_memory_update_task,
    run_self_review_chat_memory_task,
    run_self_review_document_memory_task,
    run_bot_task,
)


class TaskScheduler:
    """定时任务调度器，负责周期性和一次性任务的调度与执行。

    以可配置的轮询间隔检查到期任务，按类型分派到对应的处理函数执行，
    支持 LLM 并发槽位控制、过期任务诊断和任务取消处理。
    """

    def __init__(
        self,
        database_path: Path,
        manager: BotProcessManager,
        *,
        project_root: Path | None = None,
        poll_interval_seconds: int = 30,
    ) -> None:
        self.database_path = database_path.resolve()
        self.manager = manager
        self.project_root = Path(str(project_root)) if project_root else Path(".")
        self.poll_interval_seconds = max(5, int(poll_interval_seconds or 30))
        self.logger = get_logger("task_scheduler")
        self._loop_task: asyncio.Task[None] | None = None
        self._cached_max_concurrency: int | None = None
        self._start_lock = threading.Lock()

    def _read_max_system_task_concurrency(self) -> int:
        if self._cached_max_concurrency is not None:
            return self._cached_max_concurrency
        fallback = int(get_yaml_config().get("runtime.max_system_task_concurrency"))
        try:
            settings = load_settings_from_database(self.database_path)
            settings.fill_defaults()
            self._cached_max_concurrency = max(1, settings.runtime.max_system_task_concurrency)
            return self._cached_max_concurrency
        except Exception:
            self._cached_max_concurrency = fallback
            return fallback

    def _is_llm_dependent(self, handler_name: str) -> bool:
        return handler_name in (
            "memory_update",
            "document_memory_extraction",
            "self_review_chat_memory",
            "self_review_document_memory",
            "explicit_memory",
            "bot_task",
        )

    def start(self) -> None:
        with self._start_lock:
            if self._loop_task is not None and not self._loop_task.done():
                return
            ensure_task_runtime(self.database_path)
            reset_running_periodic_tasks(self.database_path)
            reset_running_one_time_tasks(self.database_path)
            reset_all_llm_slots(self.database_path)
            # 记录过期任务诊断日志
            overdue = list_overdue_tasks(self.database_path)
            if overdue:
                parts = [f"启动时发现 {len(overdue)} 个过期任务:"]
                for t in overdue:
                    parts.append(
                        f"  - {t['name']} | 类型={t['task_type']} | "
                        f"调度={t['schedule_type']} | 计划执行={t['next_run_at']} | "
                        f"状态={t['run_state']}"
                    )
                self.logger.warning("\n".join(parts), extra={"category": "task"})
            self._loop_task = asyncio.create_task(self._run_loop(), name="task-scheduler")

    async def stop(self) -> None:
        if self._loop_task is None:
            return
        self._loop_task.cancel()
        try:
            await self._loop_task
        except asyncio.CancelledError:
            pass
        finally:
            self._loop_task = None

    async def _run_loop(self) -> None:
        while True:
            self._cached_max_concurrency = None
            try:
                max_concurrency = self._read_max_system_task_concurrency()
                due_tasks = await asyncio.to_thread(
                    claim_due_periodic_tasks,
                    self.database_path,
                    limit=max_concurrency,
                )
                if due_tasks:
                    await asyncio.gather(
                        *(self._execute_task(task) for task in due_tasks),
                        return_exceptions=True,
                    )
                    continue
                due_one_time = await asyncio.to_thread(
                    claim_due_one_time_tasks,
                    self.database_path,
                    limit=max_concurrency,
                )
                if due_one_time:
                    serial_tasks: list[dict[str, str]] = []
                    parallel_tasks: list[dict[str, str]] = []
                    for t in due_one_time:
                        if str(t.get("handler_name", "")) == "explicit_memory":
                            serial_tasks.append(t)
                        else:
                            parallel_tasks.append(t)
                    if parallel_tasks:
                        await asyncio.gather(
                            *(self._execute_task(task) for task in parallel_tasks),
                            return_exceptions=True,
                        )
                    for t in serial_tasks:
                        await self._execute_task(t)
                    continue
                try:
                    await asyncio.to_thread(
                        cleanup_stale_llm_slots,
                        self.database_path,
                        max_age_minutes=60,
                    )
                except sqlite3.OperationalError as exc:
                    if not is_database_locked_error(exc):
                        raise
                await asyncio.sleep(self.poll_interval_seconds)
            except asyncio.CancelledError:
                raise
            except Exception:
                self.logger.exception("Task scheduler loop failed", extra={"category": "task"})
                await asyncio.sleep(self.poll_interval_seconds)

    async def _execute_task(self, task: dict[str, str]) -> None:
        task_key = str(task["task_key"])
        task_name = str(task["task_name"])
        task_type = str(task.get("task_type", ""))
        handler_name = str(task.get("handler_name", ""))
        trace_id = str(uuid4())

        # 依赖平台Agent的任务，自动执行时检查平台Agent是否已配置
        from app.db.task_store import is_agent_dependent_handler
        if is_agent_dependent_handler(handler_name):
            from app.db.settings_store import get_platform_settings
            provider = str(get_platform_settings().get("platform_agent_provider") or "").strip()
            if not provider:
                self.logger.warning(
                    "Task skipped: platform Agent not configured",
                    extra={"task_key": task_key, "category": "task"},
                )
                insert_project_log(
                    self.database_path,
                    trace_id=trace_id,
                    level="ERROR",
                    category="task",
                    source="task_scheduler",
                    message="Task failed: platform Agent not configured",
                    detail=f"task_key={task_key}\ntask_name={task_name}",
                )
                if task_type == "periodic":
                    await asyncio.to_thread(
                        mark_periodic_task_finished,
                        self.database_path,
                        task_key=task_key,
                        run_status="failed",
                        message="平台 Agent 未配置，请先在系统设置中选择平台 Agent",
                    )
                else:
                    await asyncio.to_thread(
                        mark_one_time_task_finished,
                        self.database_path,
                        task_key=task_key,
                        run_status="failed",
                        message="平台 Agent 未配置，请先在系统设置中选择平台 Agent",
                    )
                return

        needs_llm_slot = self._is_llm_dependent(handler_name)
        slot_id: str | None = None

        if needs_llm_slot:
            max_concurrency = self._read_max_system_task_concurrency()
            slot_id = await asyncio.to_thread(
                acquire_llm_slot,
                self.database_path,
                slot_type="system",
                trace_id=trace_id,
                max_concurrent=max_concurrency,
            )
            if slot_id is None:
                self.logger.warning(
                    "System task LLM concurrency limit reached, unclaiming task",
                    extra={"task_key": task_key, "category": "task"},
                )
                await asyncio.to_thread(
                    unclaim_task,
                    self.database_path,
                    task_key=task_key,
                    task_type=task_type,
                )
                return

        insert_project_log(
            self.database_path,
            trace_id=trace_id,
            level="INFO",
            category="task",
            source="task_scheduler",
            message="Task started",
            detail=f"task_key={task_key}\ntask_name={task_name}\ntask_type={task_type}\nhandler={handler_name}\nllm_slot={slot_id or 'n/a'}",
        )
        run_status = "completed"
        summary = ""
        try:
            insert_project_log(
                self.database_path,
                trace_id=trace_id,
                level="INFO",
                category="task",
                source="task_scheduler",
                message="Task handler dispatch",
                detail=f"task_key={task_key}\nhandler={handler_name}\ntask_type={task_type}",
            )
            if task_type == "periodic" and handler_name == "database_cleanup":
                result = await asyncio.to_thread(
                    run_database_cleanup_task,
                    self.database_path,
                    self.manager,
                    trace_id=trace_id,
                    source="task_scheduler",
                    category="task",
                )
                summary = (
                    f"已清理 {result['removed_messages']} 条消息、"
                    f"{result['removed_logs']} 条日志、"
                    f"{result['removed_one_time_tasks']} 条一次性任务，"
                    f"释放 {result['saved_bytes']} 字节"
                )
                await asyncio.to_thread(
                    mark_periodic_task_finished,
                    self.database_path,
                    task_key=task_key,
                    run_status="completed",
                    message=summary,
                )
            elif task_type == "one_time" and handler_name == "document_memory_extraction":
                result = await run_document_memory_extraction_task(
                    self.database_path,
                    self.project_root,
                    task,
                    trace_id=trace_id,
                )
                run_status = "completed" if result.get("extraction_ok") else "failed"
                summary = f"文档记忆提取完成: {result.get('filename', '')} ({'成功' if result.get('extraction_ok') else '失败'})"
                await asyncio.to_thread(
                    mark_one_time_task_finished,
                    self.database_path,
                    task_key=task_key,
                    run_status=run_status,
                    message=summary,
                )
            elif task_type == "one_time" and handler_name == "explicit_memory":
                result = await run_explicit_memory_task(
                    self.database_path,
                    self.project_root,
                    task,
                    trace_id=trace_id,
                )
                summary = result.get("summary", "显式记忆生成完成")
                run_status = "completed" if result.get("ok", False) else "failed"
                await asyncio.to_thread(
                    mark_one_time_task_finished,
                    self.database_path,
                    task_key=task_key,
                    run_status=run_status,
                    message=summary,
                )
            elif task_type == "periodic" and handler_name == "memory_update":
                result = await run_memory_update_task(
                    self.database_path,
                    self.project_root,
                    task,
                    trace_id=trace_id,
                )
                summary = result.get("summary", "记忆更新完成")
                if result.get("prompt_payload") is not None:
                    import json

                    await asyncio.to_thread(
                        update_periodic_task,
                        self.database_path,
                        task_key=task_key,
                        prompt_text=json.dumps(result.get("prompt_payload") or {}, ensure_ascii=False),
                    )
                if result.get("requires_manual_review") or result.get("next_batch_required"):
                    run_status = "failed"
                    summary = f"{MEMORY_UPDATE_REVIEW_REQUIRED_PREFIX} {summary}"
                else:
                    await asyncio.to_thread(
                        update_periodic_task,
                        self.database_path,
                        task_key=task_key,
                        prompt_text="",
                    )
                    run_status = "completed" if result.get("fail_count", 0) == 0 else "failed"
                await asyncio.to_thread(
                    mark_periodic_task_finished,
                    self.database_path,
                    task_key=task_key,
                    run_status=run_status,
                    message=summary,
                )
            elif task_type == "periodic" and handler_name == "self_review_chat_memory":
                result = await run_self_review_chat_memory_task(
                    self.database_path,
                    self.project_root,
                    task,
                    trace_id=trace_id,
                )
                summary = result.get("summary", "聊天记录记忆审查完成")
                run_status = "completed" if result.get("ok", False) else "failed"
                await asyncio.to_thread(
                    mark_periodic_task_finished,
                    self.database_path,
                    task_key=task_key,
                    run_status=run_status,
                    message=summary,
                )
            elif task_type == "periodic" and handler_name == "self_review_document_memory":
                result = await run_self_review_document_memory_task(
                    self.database_path,
                    self.project_root,
                    task,
                    trace_id=trace_id,
                )
                summary = result.get("summary", "文档记忆审查完成")
                run_status = "completed" if result.get("ok", False) else "failed"
                await asyncio.to_thread(
                    mark_periodic_task_finished,
                    self.database_path,
                    task_key=task_key,
                    run_status=run_status,
                    message=summary,
                )
            elif handler_name == "bot_task":
                result = await run_bot_task(
                    self.database_path,
                    self.project_root,
                    task,
                    trace_id=trace_id,
                )
                summary = result.get("summary", "任务执行完成")
                run_status = "completed" if result.get("ok", False) else "failed"
                if task_type == "one_time":
                    await asyncio.to_thread(
                        mark_one_time_task_finished,
                        self.database_path,
                        task_key=task_key,
                        run_status=run_status,
                        message=summary,
                    )
                else:
                    await asyncio.to_thread(
                        mark_periodic_task_finished,
                        self.database_path,
                        task_key=task_key,
                        run_status=run_status,
                        message=summary,
                    )
                    if run_status == "failed" and "Bot 不在线" in summary:
                        # Bot 不在线时禁用周期任务
                        await asyncio.to_thread(
                            disable_periodic_task,
                            self.database_path,
                            task_key=task_key,
                        )
            else:
                raise RuntimeError(f"Unsupported task: type={task_type}, handler={handler_name}")
            insert_project_log(
                self.database_path,
                trace_id=trace_id,
                level="INFO",
                category="task",
                source="task_scheduler",
                message="Task completed",
                detail=f"task_key={task_key}\nhandler={handler_name}\nrun_status={run_status}\nsummary={summary}",
            )
        except asyncio.CancelledError:
            self.logger.warning(
                "Task cancelled during execution, unclaiming task",
                extra={"task_key": task_key, "category": "task"},
            )
            await asyncio.to_thread(
                unclaim_task,
                self.database_path,
                task_key=task_key,
                task_type=task_type,
            )
            raise
        except Exception as exc:
            exc_info = traceback.format_exc()
            short_message = str(exc)[:2000]
            if task_type == "periodic":
                await asyncio.to_thread(
                    mark_periodic_task_finished,
                    self.database_path,
                    task_key=task_key,
                    run_status="failed",
                    message=short_message,
                )
            elif task_type == "one_time":
                await asyncio.to_thread(
                    mark_one_time_task_finished,
                    self.database_path,
                    task_key=task_key,
                    run_status="failed",
                    message=short_message,
                )
            insert_project_log(
                self.database_path,
                trace_id=trace_id,
                level="ERROR",
                category="task",
                source="task_scheduler",
                message="Task failed",
                detail=f"task_key={task_key}\nhandler={handler_name}\ntask_type={task_type}\nerror={exc_info[:1200]}",
            )
            self.logger.exception(
                "Task execution failed",
                extra={"category": "task", "trace_id": trace_id},
            )
        finally:
            if slot_id is not None:
                try:
                    await asyncio.to_thread(
                        release_llm_slot,
                        self.database_path,
                        slot_id=slot_id,
                    )
                except Exception:
                    self.logger.exception(
                        "Failed to release LLM slot",
                        extra={"slot_id": slot_id, "category": "task"},
                    )
                else:
                    insert_project_log(
                        self.database_path,
                        trace_id=trace_id,
                        level="INFO",
                        category="task",
                        source="task_scheduler",
                        message="LLM slot released",
                        detail=f"task_key={task_key}\nslot_id={slot_id}",
                    )
