# -*- coding: utf-8 -*-
"""Bot 抽象基类定义。

定义所有平台 Bot 实例的生命周期接口，为二期多平台扩展预留抽象层。
"""

import abc
import time
import threading
from typing import Any

from loguru import logger


class BaseBot(abc.ABC):
    """Bot 实例抽象基类。

    定义统一的生命周期管理接口，所有平台实现必须继承此类。

    Attributes:
        bot_id: Bot 实例唯一标识。
        config: Bot 配置字典。
    """

    def __init__(self, *, bot_id: str, config: dict[str, Any]) -> None:
        """初始化 BaseBot。

        Args:
            bot_id: Bot 实例唯一标识。
            config: Bot 配置字典。
        """
        self.bot_id: str = bot_id
        self.config: dict[str, Any] = config
        self._thread: threading.Thread | None = None
        self._is_running: bool = False
        self._start_time: float | None = None
        self._last_error: str | None = None

    @property
    def is_running(self) -> bool:
        """返回 Bot 是否正在运行。"""
        return self._is_running and self._thread is not None and self._thread.is_alive()

    @property
    def thread_id(self) -> int | None:
        """返回 Bot 运行所在的线程 ID。"""
        if self._thread is not None and self._thread.is_alive():
            return self._thread.ident
        return None

    @property
    def uptime_seconds(self) -> float | None:
        """返回 Bot 运行时长（秒）。"""
        if self._start_time is not None and self.is_running:
            return time.time() - self._start_time
        return None

    @property
    def last_error(self) -> str | None:
        """返回最近一次异常信息。"""
        return self._last_error

    def start(self) -> None:
        """启动 Bot 实例。

        在独立子线程中启动 Bot 的主循环。
        """
        if self.is_running:
            logger.warning("[BotID: {}] Bot 已在运行，跳过启动", self.bot_id)
            return

        self._is_running = True
        self._start_time = time.time()
        self._last_error = None
        self._thread = threading.Thread(
            target=self._safe_run,
            name=f"bot-{self.bot_id}",
            daemon=True,
        )
        self._thread.start()
        logger.info("[BotID: {}] Bot 子线程已启动", self.bot_id)

    def stop(self) -> None:
        """停止 Bot 实例。

        子类应在 _on_stop 中实现具体的停止逻辑（如断开 WebSocket）。
        """
        if not self._is_running:
            logger.warning("[BotID: {}] Bot 未在运行", self.bot_id)
            return

        logger.info("[BotID: {}] 正在停止 Bot...", self.bot_id)
        self._is_running = False
        self._on_stop()
        if self._thread is not None:
            self._thread.join(timeout=10.0)
            if self._thread.is_alive():
                logger.warning("[BotID: {}] 线程未能在超时内退出", self.bot_id)
        self._thread = None
        self._start_time = None
        logger.info("[BotID: {}] Bot 已停止", self.bot_id)

    def _safe_run(self) -> None:
        """线程安全的运行包装器，捕获异常并记录。"""
        try:
            self._run()
        except Exception as exc:
            self._last_error = str(exc)
            self._is_running = False
            logger.error(
                "[BotID: {}] Bot 运行异常退出: {}",
                self.bot_id,
                exc,
            )

    @abc.abstractmethod
    def _run(self) -> None:
        """Bot 主运行逻辑，子类必须实现。"""
        pass

    @abc.abstractmethod
    def _on_stop(self) -> None:
        """停止时的清理逻辑，子类必须实现。"""
        pass
