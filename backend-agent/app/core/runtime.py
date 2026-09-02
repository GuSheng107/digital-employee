"""Agent 运行时生命周期状态管理。"""

from __future__ import annotations

import asyncio
import logging
from enum import StrEnum

logger = logging.getLogger("backend_agent.runtime")


class RuntimeStatus(StrEnum):
    """Agent 运行时状态。"""

    CREATED = "created"
    STARTING = "starting"
    READY = "ready"
    STOPPING = "stopping"
    STOPPED = "stopped"


class RuntimeManager:
    """管理 Agent 运行时的幂等启动和停止。"""

    def __init__(self) -> None:
        self._status = RuntimeStatus.CREATED
        self._lock = asyncio.Lock()

    @property
    def status(self) -> RuntimeStatus:
        """返回当前运行时状态。"""
        return self._status

    @property
    def is_ready(self) -> bool:
        """返回运行时是否已接受请求。"""
        return self._status is RuntimeStatus.READY

    async def start(self) -> None:
        """初始化 Agent 运行时。"""
        async with self._lock:
            if self._status is RuntimeStatus.READY:
                return
            if self._status in {RuntimeStatus.STARTING, RuntimeStatus.STOPPING}:
                raise RuntimeError(f"运行时无法从 {self._status} 状态启动")
            self._status = RuntimeStatus.STARTING
            try:
                await self._initialize_resources()
            except Exception:
                self._status = RuntimeStatus.STOPPED
                logger.exception("Agent runtime initialization failed")
                raise
            self._status = RuntimeStatus.READY
            logger.info("Agent runtime is ready")

    async def stop(self) -> None:
        """停止 Agent 运行时并释放资源。"""
        async with self._lock:
            if self._status in {RuntimeStatus.CREATED, RuntimeStatus.STOPPED}:
                self._status = RuntimeStatus.STOPPED
                return
            if self._status is RuntimeStatus.STOPPING:
                return
            self._status = RuntimeStatus.STOPPING
            try:
                await self._release_resources()
            finally:
                self._status = RuntimeStatus.STOPPED
                logger.info("Agent runtime stopped")

    async def _initialize_resources(self) -> None:
        """预留后续消息消费者和模型客户端初始化入口。"""
        await asyncio.sleep(0)

    async def _release_resources(self) -> None:
        """预留后续消息消费者和模型客户端释放入口。"""
        await asyncio.sleep(0)
