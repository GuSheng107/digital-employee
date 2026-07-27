import json
from typing import Any

from redis import Redis

from app.core.config import settings


class RedisClientWrapper:
    """Centralized Redis wrapper for cache primitives used by services."""

    def __init__(self) -> None:
        self.redis_url = settings.redis_url
        self.client: Redis | None = None

    def init_client(self) -> None:
        if self.client is not None:
            return
        self.client = Redis.from_url(
            self.redis_url,
            decode_responses=True,
            socket_connect_timeout=settings.dependency_timeout_seconds,
            socket_timeout=settings.dependency_timeout_seconds,
        )

    def ping(self) -> bool:
        return bool(self._require_client().ping())

    def set(
        self,
        key: str,
        value: str,
        *,
        ttl_seconds: int | None = None,
    ) -> bool:
        return bool(self._require_client().set(key, value, ex=ttl_seconds))

    def get(self, key: str) -> str | None:
        value = self._require_client().get(key)
        return str(value) if value is not None else None

    def delete(self, key: str) -> int:
        return int(self._require_client().delete(key))

    def set_json(
        self,
        key: str,
        value: Any,
        *,
        ttl_seconds: int | None = None,
    ) -> bool:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return self.set(key, payload, ttl_seconds=ttl_seconds)

    def get_json(self, key: str) -> Any:
        value = self.get(key)
        if value is None:
            return None
        return json.loads(value)

    def _require_client(self) -> Redis:
        self.init_client()
        if self.client is None:
            raise RuntimeError("Redis client is not initialized.")
        return self.client


_redis_client_wrapper: RedisClientWrapper | None = None


def get_redis_client() -> RedisClientWrapper:
    global _redis_client_wrapper
    if _redis_client_wrapper is None:
        _redis_client_wrapper = RedisClientWrapper()
    return _redis_client_wrapper
