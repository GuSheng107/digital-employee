"""backend-agent 测试共享配置。"""

from __future__ import annotations

import os
from collections.abc import Iterator

import pytest
from nacos_client import NacosClient


class _FakeNacosClient:
    """测试用 Nacos 客户端。"""

    def load_to_environ(self) -> dict[str, object]:
        """注入测试配置并返回模拟配置。"""
        os.environ.setdefault("AGENT_PORT", "8030")
        os.environ.setdefault("DATA_BASE_URL", "http://127.0.0.1:8010")
        return {"agent": {"port": 8030}}


def _fake_from_env_required(cls: type[NacosClient]) -> _FakeNacosClient:
    """返回测试用 Nacos 客户端。"""
    del cls
    return _FakeNacosClient()


NacosClient.from_env_required = classmethod(_fake_from_env_required)  # type: ignore[method-assign]
os.environ.setdefault("APP_ENV", "test")
os.environ.setdefault("NACOS_SERVER_ADDR", "test-nacos:8848")
os.environ.setdefault("NACOS_USERNAME", "test")
os.environ.setdefault("NACOS_PASSWORD", "test")


@pytest.fixture(autouse=True)
def restore_runtime_environment() -> Iterator[None]:
    """在每个测试后清理可变配置缓存。"""
    yield
    from app.core.config import get_settings

    get_settings.cache_clear()
