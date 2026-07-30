"""backend-data 内部会话与强制改密状态服务。

Redis 的所有 token、会话集合和强制改密标志都只在 backend-data 读写。
"""

from __future__ import annotations

from api_common import TokenInvalidError

from app.core.config import settings
from app.core.redis_client import (
    RateLimitCounterEntry,
    RateLimitCounterResult,
    get_redis_client,
)


class IdentitySessionService:
    """管理 opaque 双 token、单会话撤销和强制改密标志。"""

    def __init__(self) -> None:
        self._redis = get_redis_client()
        self._token_prefix = settings.token_redis_prefix
        self._access_ttl = settings.access_token_ttl_seconds
        self._refresh_ttl = settings.refresh_token_ttl_seconds
        self._password_change_prefix = settings.password_change_redis_prefix

    def issue_token_pair(
        self,
        *,
        user_id: int,
        access_token: str,
        refresh_token: str,
    ) -> dict:
        """写入一对 access/refresh token 及其单会话标记。"""
        return self.replace_token_pair(
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
        )

    def read_access_token(self, access_token: str) -> int | None:
        """读取 access token 对应用户。"""
        return self._read_token("access", access_token)

    def read_refresh_token(self, refresh_token: str) -> int | None:
        """读取 refresh token 对应用户。"""
        return self._read_token("refresh", refresh_token)

    def was_access_session_replaced(self, access_token: str) -> bool:
        """判断 access token 是否因同账号新登录而失效。"""
        return self._redis.exists(
            f"{self._token_prefix}:replaced-access:{access_token}"
        )

    def rotate_token_pair(
        self,
        *,
        old_refresh_token: str,
        user_id: int,
        new_access_token: str,
        new_refresh_token: str,
    ) -> dict:
        """撤销旧配对 token，并写入新 token 对。"""
        rotated = self._redis.rotate_user_token_pair(
            old_refresh_key=self._refresh_key(old_refresh_token),
            old_pair_key=self._pair_key(old_refresh_token),
            user_tokens_key=self._user_tokens_key(user_id),
            new_access_key=self._access_key(new_access_token),
            new_refresh_key=self._refresh_key(new_refresh_token),
            new_pair_key=self._pair_key(new_refresh_token),
            access_key_prefix=f"{self._token_prefix}:access:",
            expected_user_id=user_id,
            old_refresh_token=old_refresh_token,
            new_access_token=new_access_token,
            new_refresh_token=new_refresh_token,
            access_ttl_seconds=self._access_ttl,
            refresh_ttl_seconds=self._refresh_ttl,
        )
        if not rotated:
            raise TokenInvalidError(message="refresh_token 无效或已被使用")
        return self._token_metadata(user_id)

    def replace_token_pair(
        self,
        *,
        user_id: int,
        access_token: str,
        refresh_token: str,
    ) -> dict:
        """原子替换用户旧会话，保证并发登录后只保留一对 token。"""
        self._redis.replace_user_token_pair(
            user_tokens_key=self._user_tokens_key(user_id),
            access_key=self._access_key(access_token),
            refresh_key=self._refresh_key(refresh_token),
            pair_key=self._pair_key(refresh_token),
            access_key_prefix=f"{self._token_prefix}:access:",
            refresh_key_prefix=f"{self._token_prefix}:refresh:",
            pair_key_prefix=f"{self._token_prefix}:pair:",
            replaced_access_key_prefix=f"{self._token_prefix}:replaced-access:",
            user_id=user_id,
            access_token=access_token,
            refresh_token=refresh_token,
            access_ttl_seconds=self._access_ttl,
            refresh_ttl_seconds=self._refresh_ttl,
        )
        return self._token_metadata(user_id)

    def logout(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
    ) -> None:
        """撤销当前 access token 所属的完整会话。"""
        user_id = self.read_access_token(access_token)
        if user_id is None and refresh_token:
            user_id = self.read_refresh_token(refresh_token)
        if user_id is not None:
            self.revoke_all_user_tokens(user_id)
            return
        self._redis.delete(self._access_key(access_token))
        if refresh_token:
            self._redis.delete(
                self._refresh_key(refresh_token),
                self._pair_key(refresh_token),
            )

    def revoke_token(
        self,
        kind: str,
        token: str,
        *,
        user_id: int | None = None,
    ) -> None:
        """撤销一个 token；若属于当前会话则撤销整对 token。"""
        if user_id is not None:
            current_pair = self._redis.read_user_token_pair(
                self._user_tokens_key(user_id)
            )
            if current_pair and token in current_pair.values():
                self.revoke_all_user_tokens(user_id)
                return
        self._redis.delete(self._token_key(kind, token))

    def revoke_all_user_tokens(self, user_id: int) -> None:
        """撤销用户全部 access、refresh、pair token。"""
        self._redis.revoke_user_token_pair(
            user_tokens_key=self._user_tokens_key(user_id),
            access_key_prefix=f"{self._token_prefix}:access:",
            refresh_key_prefix=f"{self._token_prefix}:refresh:",
            pair_key_prefix=f"{self._token_prefix}:pair:",
        )

    def require_password_change(self, user_id: int) -> None:
        """设置持久强制改密标志，直到用户主动修改密码。"""
        self._redis.set(self._password_change_key(user_id), "1")

    def clear_password_change_required(self, user_id: int) -> None:
        """清除强制改密标志。"""
        self._redis.delete(self._password_change_key(user_id))

    def is_password_change_required(self, user_id: int) -> bool:
        """判断用户是否必须修改密码。"""
        return self._redis.get(self._password_change_key(user_id)) == "1"

    def increment_rate_limit(self, *, key: str, window_seconds: int) -> int:
        """消费固定窗口限流计数。"""
        return self._redis.increment_with_ttl(
            key,
            ttl_seconds=window_seconds,
        )

    def increment_rate_limit_with_ttl(
        self,
        *,
        key: str,
        window_seconds: int,
    ) -> tuple[int, int]:
        """消费固定窗口限流计数并返回剩余秒数。"""
        return self._redis.increment_with_ttl_result(
            key,
            ttl_seconds=window_seconds,
        )

    def increment_rate_limits_with_ttl(
        self,
        entries: list[RateLimitCounterEntry],
    ) -> list[RateLimitCounterResult]:
        """按优先级在一个 Redis 事务中消费多个限流桶。"""
        return self._redis.increment_many_with_ttl_results(entries)

    def get_rate_limit_ttl(self, key: str) -> int:
        """读取限流窗口剩余秒数。"""
        return max(1, self._redis.ttl(key))

    def reset_rate_limit(self, key: str) -> None:
        """清除指定限流桶。"""
        self._redis.delete(key)

    def reset_rate_limits(self, keys: list[str]) -> None:
        """在一次 Redis 调用中清除多个限流桶。"""
        if not keys:
            return
        self._redis.delete(*keys)

    def _read_token(self, kind: str, token: str) -> int | None:
        raw = self._redis.get(self._token_key(kind, token))
        if raw is None:
            return None
        try:
            user_id = int(raw)
        except (TypeError, ValueError):
            return None
        current_pair = self._redis.read_user_token_pair(self._user_tokens_key(user_id))
        expected_token = (
            current_pair.get(f"{kind}_token") if current_pair is not None else None
        )
        return user_id if expected_token == token else None

    def _access_key(self, token: str) -> str:
        return f"{self._token_prefix}:access:{token}"

    def _refresh_key(self, token: str) -> str:
        return f"{self._token_prefix}:refresh:{token}"

    def _pair_key(self, refresh_token: str) -> str:
        return f"{self._token_prefix}:pair:{refresh_token}"

    def _token_key(self, kind: str, token: str) -> str:
        if kind == "access":
            return self._access_key(token)
        if kind == "refresh":
            return self._refresh_key(token)
        raise ValueError(f"unknown token kind: {kind}")

    def _user_tokens_key(self, user_id: int) -> str:
        return f"{self._token_prefix}:user:{user_id}:tokens"

    def _password_change_key(self, user_id: int) -> str:
        return f"{self._password_change_prefix}:{user_id}"

    def _token_metadata(self, user_id: int) -> dict:
        return {
            "access_expires_in": self._access_ttl,
            "refresh_expires_in": self._refresh_ttl,
            "user_id": user_id,
            "must_change_password": self.is_password_change_required(user_id),
        }
