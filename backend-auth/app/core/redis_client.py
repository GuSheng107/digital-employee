"""Redis 客户端封装。

承载双 token 体系的核心存储：
- access_token  -> user_id（短 TTL，业务接口鉴权）
- refresh_token -> user_id（长 TTL，换取新 access_token）
- 用户活跃 token 集合（用于全量登出）

各后端服务可本地直连同一 Redis 实例验证 access_token，
实现去中心化鉴权，不依赖 auth 服务在线。
"""

from __future__ import annotations

import json
from typing import Any

from redis import Redis

from app.core.config import settings


class RedisClient:
    """Redis 客户端封装，提供字符串与 JSON 两种读写模式。

    连接懒加载，首次访问时建立，复用单例 client。decode_responses=True
    让所有返回值为 str 而非 bytes，便于直接传递给业务代码。
    """

    def __init__(self) -> None:
        self.redis_url = settings.redis_url
        self._client: Redis | None = None

    def init_client(self) -> None:
        """初始化 Redis 连接，已初始化时跳过。"""
        if self._client is not None:
            return
        self._client = Redis.from_url(
            self.redis_url,
            decode_responses=True,
            socket_connect_timeout=settings.dependency_timeout_seconds,
            socket_timeout=settings.dependency_timeout_seconds,
        )

    def ping(self) -> bool:
        """探活 Redis，返回 True 表示连接正常。"""
        return bool(self._require_client().ping())

    def set(
        self,
        key: str,
        value: str,
        *,
        ttl_seconds: int | None = None,
    ) -> bool:
        """写入字符串值，可选 TTL。"""
        return bool(self._require_client().set(key, value, ex=ttl_seconds))

    def get(self, key: str) -> str | None:
        """读取字符串值，不存在时返回 None。"""
        value = self._require_client().get(key)
        return str(value) if value is not None else None

    def delete(self, *keys: str) -> int:
        """删除一个或多个 key，返回实际删除数量。"""
        return int(self._require_client().delete(*keys))

    def sadd(self, key: str, *members: str) -> int:
        """向集合添加成员，返回新增数量。"""
        return int(self._require_client().sadd(key, *members))

    def srem(self, key: str, *members: str) -> int:
        """从集合移除成员，返回移除数量。"""
        return int(self._require_client().srem(key, *members))

    def smembers(self, key: str) -> set[str]:
        """返回集合中的所有成员。"""
        return set(self._require_client().smembers(key))

    def expire(self, key: str, ttl_seconds: int) -> bool:
        """为 key 设置 TTL，返回是否成功。"""
        return bool(self._require_client().expire(key, ttl_seconds))

    def set_json(
        self,
        key: str,
        value: Any,
        *,
        ttl_seconds: int | None = None,
    ) -> bool:
        """将对象 JSON 序列化后写入。"""
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return self.set(key, payload, ttl_seconds=ttl_seconds)

    def get_json(self, key: str) -> Any:
        """读取 JSON 字符串并反序列化，不存在时返回 None。"""
        value = self.get(key)
        if value is None:
            return None
        return json.loads(value)

    def _require_client(self) -> Redis:
        """确保客户端已初始化并返回。"""
        self.init_client()
        if self._client is None:
            raise RuntimeError("Redis client is not initialized.")
        return self._client


_redis_client: RedisClient | None = None


def get_redis_client() -> RedisClient:
    """获取全局 Redis 客户端单例。"""
    global _redis_client
    if _redis_client is None:
        _redis_client = RedisClient()
    return _redis_client
