from time import perf_counter
from typing import Callable

from app.core.config import ConnectionTarget
from app.core.database import DatabaseRole, get_database_client
from app.core.minio_client import get_minio_client
from app.core.redis_client import get_redis_client
from app.schemas.health import DependencyStatus, DependenciesStatus


def _measure(check: Callable[[], None]) -> DependencyStatus:
    start = perf_counter()
    try:
        check()
        latency_ms = round((perf_counter() - start) * 1000, 2)
        return DependencyStatus(ok=True, message="ok", latency_ms=latency_ms)
    except Exception as exc:
        latency_ms = round((perf_counter() - start) * 1000, 2)
        return DependencyStatus(ok=False, message=str(exc), latency_ms=latency_ms)


def _check_database(role: DatabaseRole) -> None:
    get_database_client(role).ping()


def _check_redis() -> None:
    client = get_redis_client()
    client.ping()


def _check_minio() -> None:
    client = get_minio_client()
    client.list_buckets()


class HealthService:
    def test_dependencies(
        self,
        target: ConnectionTarget = "all",
    ) -> DependenciesStatus:
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
