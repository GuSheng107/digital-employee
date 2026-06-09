from __future__ import annotations

"""Bot 子进程生命周期管理模块。

管理 Bot 子进程的启动、停止、重启以及崩溃检测，
包括进程输出捕获、PID 文件管理、崩溃事件记录和日志持久化。
"""

import io
import logging
import os
import re
import subprocess
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Any

from app.database import default_database_path
from app.db.log_store import insert_bot_process_log, get_bot_process_logs
from app.logger import get_logger
from app.process_utils import is_process_running, read_pid_file, remove_pid_file, stop_process


class CrashEvent:
    """Bot 进程崩溃事件，记录崩溃的 Bot 标识、退出码、时间戳和 stderr 尾部输出。"""

    __slots__ = ("id", "bot_key", "exit_code", "timestamp", "acknowledged", "stderr_tail")

    def __init__(self, bot_key: str, exit_code: int | None, stderr_tail: str = "") -> None:
        self.id = uuid.uuid4().hex[:12]
        self.bot_key = bot_key
        self.exit_code = exit_code
        self.timestamp = time.time()
        self.acknowledged = False
        self.stderr_tail = stderr_tail

    def to_dict(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "bot_key": self.bot_key,
            "exit_code": self.exit_code,
            "timestamp": self.timestamp,
            "stderr_tail": self.stderr_tail,
        }


class BotProcessManager:
    """Bot 子进程管理器，负责 Bot 进程的启动、停止、状态查询和崩溃检测。

    通过 subprocess 启动 Bot 子进程，使用 PID 文件跟踪运行状态，
    捕获 stdout/stderr 输出并转发到日志系统，检测已崩溃的进程并生成崩溃事件。
    """

    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root.resolve()
        self.main_script = self.project_root / "main.py"
        self.bot_processes: dict[str, subprocess.Popen[bytes]] = {}
        self._bot_output_buffers: dict[str, list[str]] = {}
        self._crash_events: list[CrashEvent] = []
        self._lock = threading.Lock()
        self.database_path = default_database_path(project_root)

    def status(self, bot_key: str) -> dict[str, Any]:
        with self._lock:
            pid = self._running_pid(bot_key)
            process = self.bot_processes.get(bot_key)
        if pid is None and process is not None and process.poll() is None:
            pid = process.pid
        return {"running": pid is not None, "pid": pid}

    def all_statuses(self, bots: list[dict[str, Any]]) -> dict[str, Any]:
        return {
            str(bot["bot_key"]): self.status(str(bot["bot_key"]))
            for bot in bots
        }

    def start(self, bot_key: str) -> dict[str, Any]:
        with self._lock:
            if self._running_pid(bot_key) is not None:
                return self.status(bot_key)

        args = [
            str(Path(sys.executable)),
            str(self.main_script),
            "--run-bot",
            "--project-root",
            str(self.project_root),
            "--parent-pid",
            str(os.getpid()),
            "--bot-key",
            bot_key,
        ]
        creationflags = getattr(subprocess, "CREATE_NO_WINDOW", 0)
        
        with self._lock:
            self._bot_output_buffers[bot_key] = []
        
        try:
            process = subprocess.Popen(
                args,
                cwd=str(self.project_root),
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                creationflags=creationflags,
            )
        except Exception:
            with self._lock:
                self._bot_output_buffers.pop(bot_key, None)
            raise
        
        with self._lock:
            self.bot_processes[bot_key] = process
        
        # 启动两个线程分别读取 stdout 和 stderr
        stdout_thread = threading.Thread(
            target=self._read_output,
            args=(bot_key, process.stdout, "stdout"),
            daemon=True
        )
        stderr_thread = threading.Thread(
            target=self._read_output,
            args=(bot_key, process.stderr, "stderr"),
            daemon=True
        )
        stdout_thread.start()
        stderr_thread.start()
        
        self._wait_for_startup(bot_key)
        return self.status(bot_key)

    def _read_output(self, bot_key: str, pipe: io.BufferedReader, pipe_type: str) -> None:
        logger = get_logger("bot_process")
        _LOG_LINE_RE = re.compile(
            r'^\d{4}-\d{2}-\d{2} \d{2}:\d{2}:\d{2} (\w+)\s+([\w.]+) - (.*)$'
        )
        pending_lines: list[str] = []
        last_extra: dict[str, str] = {}
        last_level = logging.INFO

        def _flush_pending() -> None:
            nonlocal pending_lines
            if not pending_lines:
                return
            combined = "\n".join(pending_lines)
            pending_lines = []
            logger.log(
                last_level,
                "[%s] %s",
                bot_key[:12],
                combined,
                extra=last_extra,
            )

        try:
            for line in pipe:
                try:
                    line_str = line.decode("utf-8", errors="replace").rstrip("\r\n")
                    if not line_str:
                        continue

                    log_match = _LOG_LINE_RE.match(line_str)

                    if log_match:
                        _flush_pending()
                        level_name, message = log_match.groups()
                        last_level = getattr(logging, level_name, logging.INFO)

                        extra: dict[str, str] = {}
                        if "trace_id=" in message:
                            trace_match = re.search(r'trace_id=([\w\-]+)', message)
                            if trace_match:
                                extra["trace_id"] = trace_match.group(1)
                        if "category=" in message:
                            cat_match = re.search(r'category=(\w+)', message)
                            if cat_match:
                                extra["category"] = cat_match.group(1)
                        last_extra = extra

                        logger.log(last_level, "[%s] %s", bot_key[:12], line_str, extra=extra)
                    else:
                        if pipe_type == "stderr":
                            last_level = logging.ERROR
                        pending_lines.append(line_str)

                    with self._lock:
                        if bot_key in self._bot_output_buffers:
                            self._bot_output_buffers[bot_key].append(line_str + "\n")
                except Exception:
                    pass
            _flush_pending()
        except Exception:
            pass

    def stop(self, bot_key: str) -> dict[str, Any]:
        with self._lock:
            pid = self._running_pid(bot_key)
            process = self.bot_processes.pop(bot_key, None)
            buffer = self._bot_output_buffers.pop(bot_key, None)
        
        if buffer:
            try:
                insert_bot_process_log(
                    self.database_path,
                    bot_key=bot_key,
                    content="".join(buffer),
                )
            except Exception:
                pass
        
        if process is not None and process.poll() is None:
            try:
                process.terminate()
                process.wait(timeout=3)
            except Exception:
                stop_process(process.pid)

        if pid is not None and is_process_running(pid):
            stop_process(pid)

        remove_pid_file(self._pid_file(bot_key))
        return self.status(bot_key)

    def stop_all(self) -> None:
        with self._lock:
            keys = set(self.bot_processes)
        data_dir = self.project_root / "data"
        if data_dir.exists():
            for file in data_dir.glob("bot-*.pid"):
                key = file.stem.replace("bot-", "", 1)
                keys.add(key)
        for key in keys:
            self.stop(key)

    def check_crashed_bots(self) -> list[CrashEvent]:
        crashed_events: list[CrashEvent] = []
        persisted_buffers: list[tuple[str, str]] = []
        with self._lock:
            for bot_key, process in list(self.bot_processes.items()):
                return_code = process.poll()
                if return_code is None:
                    continue
                buffer = self._bot_output_buffers.pop(bot_key, [])
                stderr_tail = "".join(buffer[-50:]).strip()
                self.bot_processes.pop(bot_key, None)
                # 清理 pid 文件
                remove_pid_file(self._pid_file(bot_key))
                self._crash_events.append(
                    CrashEvent(bot_key, return_code, stderr_tail=stderr_tail)
                )
                crashed_events.append(self._crash_events[-1])
                if buffer:
                    persisted_buffers.append((bot_key, "".join(buffer)))
        for bot_key, content in persisted_buffers:
            try:
                insert_bot_process_log(
                    self.database_path,
                    bot_key=bot_key,
                    content=content,
                )
            except Exception:
                pass
        return crashed_events

    def get_unacknowledged_crashes(self) -> list[dict[str, Any]]:
        with self._lock:
            return [e.to_dict() for e in self._crash_events if not e.acknowledged]

    def acknowledge_crash(self, event_id: str) -> bool:
        with self._lock:
            for event in self._crash_events:
                if event.id == event_id and not event.acknowledged:
                    event.acknowledged = True
                    return True
        return False

    def acknowledge_all_crashes(self) -> int:
        with self._lock:
            count = 0
            for event in self._crash_events:
                if not event.acknowledged:
                    event.acknowledged = True
                    count += 1
            return count

    def _pid_file(self, bot_key: str) -> Path:
        clean_key = "".join(char for char in bot_key if char.isalnum() or char in {"_", "-"})
        return self.project_root / "data" / f"bot-{clean_key or 'bot'}.pid"

    def _running_pid(self, bot_key: str) -> int | None:
        pid_file = self._pid_file(bot_key)
        pid = read_pid_file(pid_file)
        if is_process_running(pid):
            return pid
        if pid is not None:
            remove_pid_file(pid_file)
        return None

    def _wait_for_startup(self, bot_key: str) -> None:
        logger = get_logger("web_server.bot_process")
        deadline = time.time() + 5
        while time.time() < deadline:
            if self._running_pid(bot_key) is not None:
                return
            process = self.bot_processes.get(bot_key)
            if process is not None and process.poll() is not None:
                stderr_tail = self._read_stderr_tail(bot_key)
                logger.error(
                    "Bot [%s] process exited immediately with code %d. stderr:\n%s",
                    bot_key, process.returncode, stderr_tail,
                    extra={"category": "bot"},
                )
                return
            time.sleep(0.2)

    def _read_stderr_tail(self, bot_key: str, max_lines: int = 50) -> str:
        with self._lock:
            buffer = self._bot_output_buffers.get(bot_key, [])
        
        if buffer:
            return "".join(buffer[-max_lines:]).strip()
        
        return get_bot_process_logs(
            self.database_path,
            bot_key=bot_key,
            max_lines=max_lines,
        )
