"""同账号单会话 token 撤销测试。"""

from __future__ import annotations

from typing import Any

from app.services.auth_service import AuthService


class _FakeRedis:
    """记录单会话清理涉及的 Redis 操作。"""

    def __init__(self, tokens: set[str]) -> None:
        self.tokens = tokens
        self.deleted_keys: tuple[str, ...] = ()

    def smembers(self, _key: str) -> set[str]:
        """返回预置活跃 token。"""
        return self.tokens

    def delete(self, *keys: str) -> int:
        """记录批量删除 key。"""
        self.deleted_keys = keys
        return len(keys)

    def __getattr__(self, name: str) -> Any:
        """未预期的方法调用直接失败，避免测试误放行。"""
        raise AssertionError(f"unexpected redis method: {name}")


def test_revoke_all_user_tokens_removes_access_refresh_pair_and_set() -> None:
    """后登录必须同时清除旧 access、refresh、pair 与用户 token 集合。"""
    redis = _FakeRedis({"access-token", "refresh-token"})
    service = AuthService.__new__(AuthService)
    service._redis = redis
    service._prefix = "auth"

    service._revoke_all_user_tokens(7)

    assert set(redis.deleted_keys) == {
        "auth:user:7:tokens",
        "auth:access:access-token",
        "auth:refresh:access-token",
        "auth:pair:access-token",
        "auth:access:refresh-token",
        "auth:refresh:refresh-token",
        "auth:pair:refresh-token",
    }
