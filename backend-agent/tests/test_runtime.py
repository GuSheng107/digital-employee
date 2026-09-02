"""Agent RuntimeManager 测试。"""

from __future__ import annotations

import pytest

from app.core.runtime import RuntimeManager, RuntimeStatus


@pytest.mark.asyncio
async def test_runtime_start_and_stop_changes_status() -> None:
    """运行时应按顺序进入就绪和停止状态。"""
    runtime = RuntimeManager()
    assert runtime.status is RuntimeStatus.CREATED

    await runtime.start()
    assert runtime.status is RuntimeStatus.READY
    assert runtime.is_ready is True

    await runtime.stop()
    assert runtime.status is RuntimeStatus.STOPPED
    assert runtime.is_ready is False


@pytest.mark.asyncio
async def test_runtime_start_and_stop_are_idempotent() -> None:
    """重复启动和停止不应破坏状态。"""
    runtime = RuntimeManager()
    await runtime.start()
    await runtime.start()
    await runtime.stop()
    await runtime.stop()
    assert runtime.status is RuntimeStatus.STOPPED
