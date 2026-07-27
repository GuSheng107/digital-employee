from time import perf_counter
from typing import Callable

from app.core.config import ConnectionTarget
from app.core.database import DatabaseRole, get_database_client
from app.core.minio_client import get_minio_client
from app.core.redis_client import get_redis_client
from app.schemas.health import DependencyStatus, DependenciesStatus


def _measure(check: Callable[[], None]) -> DependencyStatus:
    """执行一次依赖探活并测量耗时。

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


def _check_database(role: DatabaseRole) -> None:
    """对指定角色的 PostgreSQL 数据库执行一次 ping。"""
    get_database_client(role).ping()


def _check_redis() -> None:
    """对 Redis 实例执行一次 ping。"""
    client = get_redis_client()
    client.ping()


def _check_minio() -> None:
    """对 MinIO 实例执行 list_buckets 探活。"""
    client = get_minio_client()
    client.list_buckets()


class HealthService:
    """依赖健康检查业务编排层。"""

    def test_dependencies(
        self,
        target: ConnectionTarget = "all",
    ) -> DependenciesStatus:
        """按目标维度执行依赖探活。

        Args:
            target: 探活目标，可选 all/postgres/core_db/vector_db/redis/minio。

        Returns:
            各依赖的探活状态汇总对象。
        """
        enabled = {
            "core_db": target in {"all", "postgres", "core_db"},
            "vector_db": target in {"all", "postgres", "vector_db"},
            "redis": target in {"all", "redis"},
            "minio": target in {"all", "minio"},
        }

        skipped = DependencyStatus(ok=True, message="skipped", latency_ms=None)
        return DependenciesStatus(
            core_db=(
                _measure(lambda: _check_database(DatabaseRole.CORE))
                if enabled["core_db"]
                else skipped
            ),
            vector_db=(
                _measure(lambda: _check_database(DatabaseRole.VECTOR))
                if enabled["vector_db"]
                else skipped
            ),
            redis=_measure(_check_redis) if enabled["redis"] else skipped,
            minio=_measure(_check_minio) if enabled["minio"] else skipped,
        )
