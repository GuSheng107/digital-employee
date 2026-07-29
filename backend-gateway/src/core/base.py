# -*- coding: utf-8 -*-
"""Bot 抽象基类定义。

定义所有平台 Bot 实例的生命周期接口，为二期多平台扩展预留抽象层。
"""

import abc
import time
import threading
from typing import Any


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

    @property
    def is_zombie(self) -> bool:
        """判断 Bot 是否处于僵尸状态。

        僵尸状态指 ``_is_running`` 标记为 True 但底层线程已不存在或已死亡，
        需要由 Watchdog 重新拉起。该属性用于将 ``_is_running`` 与 ``_thread``
        的访问收拢在 Bot 内部，避免管理器直接读取私有字段。

        Returns:
            True 表示 Bot 处于僵尸状态，需要重启；False 表示正常运行或已正常停止。
        """
        if not self._is_running:
            return False
        return self._thread is None or not self._thread.is_alive()

    def start(self) -> None:
        """启动 Bot 实例。

        在独立子线程中启动 Bot 的主循环。
        """
        if self.is_running:
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

    def stop(self) -> None:
        """停止 Bot 实例。

        子类应在 _on_stop 中实现具体的停止逻辑（如断开 WebSocket）。
        """
        if not self._is_running:
            return
        self._is_running = False
        self._on_stop()
        if self._thread is not None:
            self._thread.join(timeout=10.0)
        self._thread = None
        self._start_time = None

    def _safe_run(self) -> None:
        """线程安全的运行包装器，捕获异常并记录。"""
        try:
            self._run()
        except Exception as exc:
            self._last_error = str(exc)
            self._is_running = False

    @abc.abstractmethod
    def _run(self) -> None:
        """Bot 主运行逻辑，子类必须实现。"""
        pass

    @abc.abstractmethod
    def _on_stop(self) -> None:
        """停止时的清理逻辑，子类必须实现。"""
        pass
