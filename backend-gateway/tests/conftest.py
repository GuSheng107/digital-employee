"""backend-gateway 单测共享 fixture。"""

from __future__ import annotations

import threading
from typing import Any

import pytest

from src.core.base import BaseBot


class _StubBot(BaseBot):
    """轻量测试用 Bot 子类。

    通过 ``behavior`` 控制运行行为：
    - ``"block"``：_run 阻塞直到 _is_running 被 stop() 置 False（模拟正常运行）。
    - ``"crash"``：_run 立即抛异常退出（模拟崩溃，验证僵尸态语义）。
    - ``"exit"``：_run 立即正常返回（模拟线程退出但未崩溃）。
    """

    def __init__(
        self,
        *,
        bot_id: str,
        config: dict[str, Any],
        behavior: str = "block",
    ) -> None:
        super().__init__(bot_id=bot_id, config=config)
        self.behavior = behavior
        self._stop_event = threading.Event()
        self.stop_called: bool = False
        self.run_started: int = 0

    def _run(self) -> None:
        self.run_started += 1
        if self.behavior == "crash":
            raise RuntimeError(f"stub crash for {self.bot_id}")
        if self.behavior == "exit":
            return
        # block 模式：阻塞直到 stop 信号
        while self._is_running and not self._stop_event.is_set():
            self._stop_event.wait(timeout=0.05)

    def _on_stop(self) -> None:
        self.stop_called = True
        self._stop_event.set()


@pytest.fixture
def stub_bot_class() -> type[_StubBot]:
    """返回测试用 StubBot 类，供需要类对象的场景使用。"""
    return _StubBot


@pytest.fixture
def make_stub_bot(stub_bot_class: type[_StubBot]):
    """工厂 fixture：构造一个 StubBot 实例。"""

    def _make(
        bot_id: str = "test-bot",
        behavior: str = "block",
        mode: str = "test",
        platform: str = "feishu",
    ) -> _StubBot:
        return stub_bot_class(
            bot_id=bot_id,
            config={
                "app_id": "stub-app-id",
                "app_secret": "stub-secret",
                "mode": mode,
                "platform": platform,
            },
            behavior=behavior,
        )

    return _make
