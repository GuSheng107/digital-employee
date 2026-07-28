"""健康检查业务编排层。

探活 PostgreSQL 与 Redis 依赖，返回结构化状态供 /health/dependencies 端点。
"""

from __future__ import annotations

from collections.abc import Callable
from time import perf_counter

from app.core.config import ConnectionTarget
from app.core.database import get_database_client
from app.core.redis_client import get_redis_client
from app.schemas.health import DependenciesStatus, DependencyStatus


def _measure(check: Callable[[], None]) -> DependencyStatus:
    """执行一次探活并测量耗时。

    Args:
        check: 具体的探活回调，发生异常时视为不可用。

    Returns:
        包含 ok 标志、消息与延迟毫秒数的状态对象。
    """
    start = perf_counter()
    try:
        check()
        latency_ms = round((perf_counter() - start) * 1000, 2)
        return DependencyStatus(ok=True, message="ok", latency_ms=latency_ms)
    except Exception as exc:
        latency_ms = round((perf_counter() - start) * 1000, 2)
        return DependencyStatus(ok=False, message=str(exc), latency_ms=latency_ms)


def _check_database() -> None:
    """对 PostgreSQL 执行一次 ping。"""
    get_database_client().ping()


def _check_redis() -> None:
    """对 Redis 执行一次 ping。"""
    get_redis_client().ping()


class HealthService:
    """依赖健康检查业务编排层。"""

    def test_dependencies(
        self,
        target: ConnectionTarget = "all",
    ) -> DependenciesStatus:
        """按目标维度执行依赖探活。

        Args:
            target: 探活目标，可选 all/postgres/core_db/redis。

        Returns:
            各依赖的探活状态汇总对象。
        """
        skipped = DependencyStatus(ok=True, message="skipped", latency_ms=None)
        return DependenciesStatus(
            core_db=(
                _measure(_check_database)
                if target in {"all", "postgres", "core_db"}
                else skipped
            ),
            redis=_measure(_check_redis) if target in {"all", "redis"} else skipped,
        )
