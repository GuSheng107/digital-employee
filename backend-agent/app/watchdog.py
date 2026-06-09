from __future__ import annotations

"""Bot 进程看门狗模块。

实现 Bot 进程的监控和自动检测，定期检查已崩溃的 Bot 进程
并记录崩溃事件日志，用于后续的告警和自动重启处理。
"""

import threading
from typing import TYPE_CHECKING

from app.logger import get_logger

if TYPE_CHECKING:
    from app.bot_process_manager import BotProcessManager


class BotWatchdog:
    """Bot 进程看门狗，定期检测崩溃的 Bot 进程并记录错误日志。

    以可配置的检查间隔轮询 BotProcessManager 检测崩溃事件，
    将崩溃信息和 stderr 输出记录到日志系统。
    """

    def __init__(
        self,
        manager: BotProcessManager,
        check_interval: float = 5.0,
    ) -> None:
        self._manager = manager
        self._check_interval = check_interval
        self._stop_event = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        if self._thread is not None and self._thread.is_alive():
            return
        self._stop_event.clear()
        self._thread = threading.Thread(
            target=self._loop,
            name="bot-watchdog",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop_event.set()
        if self._thread is not None:
            self._thread.join(timeout=self._check_interval + 2)
            self._thread = None

    def _loop(self) -> None:
        logger = get_logger("watchdog")
        while not self._stop_event.is_set():
            try:
                crashed = self._manager.check_crashed_bots()
                if crashed:
                    for event in crashed:
                        logger.error(
                            "Bot [%s] process has exited unexpectedly (exit_code=%s).",
                            event.bot_key,
                            event.exit_code,
                            extra={"category": "bot"},
                        )
                        if event.stderr_tail:
                            logger.error(
                                "Bot [%s] stderr tail before exit:\n%s",
                                event.bot_key,
                                event.stderr_tail,
                                extra={"category": "bot"},
                            )
            except Exception:
                logger.exception("Watchdog check failed.", extra={"category": "bot"})
            self._stop_event.wait(timeout=self._check_interval)
