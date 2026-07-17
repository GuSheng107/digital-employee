from __future__ import annotations

"""双 Token 认证管理器 (Redis opaque token)。

access_token  (ccx_at_xxx) — 短期，滑动 TTL (默认 3h)，绝对过期上限 (默认 24h)
refresh_token (ccx_rt_xxx) — 长期，绝对 TTL (默认 7d)，刷新时立即撤销旧 RT

Redis Key 结构:
  cc:at:{sha256[:8]}  — access token session
    token_full, username, role, rt_prefix, created_at, expires_at, revoked

  cc:rt:{sha256[:8]}  — refresh token session
    token_full, username, role, at_prefix, created_at, expires_at, revoked

刷新时的 grace period (默认 15min):
  旧 access_token 保留 grace period 内有效（处理途中的请求）
  旧 refresh_token 立即标记 revoked=1
"""

import hashlib
import hmac
import secrets
import time
from base64 import urlsafe_b64encode
from typing import Any

import redis.asyncio as aioredis


def _sha256(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def _first8_hex(plain: str) -> str:
    return _sha256(plain.encode("utf-8"))[:16]  # 8 bytes = 16 hex chars


def _full_hash(plain: str) -> str:
    return _sha256(plain.encode("utf-8"))


def _generate_opaque(prefix: str) -> str:
    raw = secrets.token_bytes(32)
    return prefix + urlsafe_b64encode(raw).rstrip(b"=").decode("ascii")


class TokenUser:
    __slots__ = ("username", "role")

    def __init__(self, username: str, role: str) -> None:
        self.username = username
        self.role = role


class TokenPair:
    __slots__ = ("access_token", "refresh_token", "expires_in", "user")

    def __init__(
        self,
        access_token: str,
        refresh_token: str,
        expires_in: int,
        user: TokenUser,
    ) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.expires_in = expires_in
        self.user = user


def _hset_dict(pipe, key: str, data: dict) -> None:
    """Redis 3.0 兼容 HSET：逐个设置字段，避免 mapping 参数 (需要 Redis 4.0+)。"""
    for field, value in data.items():
        pipe.hset(key, field, value)


class DualTokenManager:
    """Redis 双 token 管理器 (access + refresh opaque tokens)."""

    def __init__(
        self,
        redis_client: aioredis.Redis,
        *,
        at_ttl_seconds: int = 3 * 60 * 60,       # access token 滑动 TTL，默认 3h
        rt_ttl_seconds: int = 7 * 24 * 60 * 60,   # refresh token 绝对 TTL，默认 7d
        at_absolute_lifetime_seconds: int = 24 * 60 * 60,  # access token 创建后绝对上限，默认 24h
        rt_grace_seconds: int = 15 * 60,           # 刷新后旧 access token 保留时间
    ) -> None:
        self._redis = redis_client
        self.at_ttl = at_ttl_seconds
        self.rt_ttl = rt_ttl_seconds
        self.at_absolute_lifetime = at_absolute_lifetime_seconds
        self.rt_grace = rt_grace_seconds

    # ── Redis key helpers ──────────────────────────────────────────

    @staticmethod
    def _at_key(hash_prefix: str) -> str:
        return f"cc:at:{hash_prefix}"

    @staticmethod
    def _rt_key(hash_prefix: str) -> str:
        return f"cc:rt:{hash_prefix}"

    # ── Issue token pair ───────────────────────────────────────────

    async def issue_token_pair(self, username: str, role: str) -> TokenPair:
        """签发新的 access + refresh token pair，写入 Redis 并双向关联。"""
        now = int(time.time())

        at_plain = _generate_opaque("ccx_at_")
        rt_plain = _generate_opaque("ccx_rt_")

        at_prefix = _first8_hex(at_plain)
        rt_prefix = _first8_hex(rt_plain)
        at_expires_at = now + self.at_ttl
        rt_expires_at = now + self.rt_ttl

        at_data = {
            "token_full": _full_hash(at_plain),
            "username": username,
            "role": role,
            "rt_prefix": rt_prefix,
            "created_at": str(now),
            "expires_at": str(at_expires_at),
            "revoked": "0",
        }
        rt_data = {
            "token_full": _full_hash(rt_plain),
            "username": username,
            "role": role,
            "at_prefix": at_prefix,
            "created_at": str(now),
            "expires_at": str(rt_expires_at),
            "revoked": "0",
        }

        async with self._redis.pipeline(transaction=True) as pipe:
            _hset_dict(pipe, self._at_key(at_prefix), at_data)
            pipe.expireat(self._at_key(at_prefix), at_expires_at + 300)
            _hset_dict(pipe, self._rt_key(rt_prefix), rt_data)
            pipe.expireat(self._rt_key(rt_prefix), rt_expires_at + 300)
            await pipe.execute()

        return TokenPair(
            access_token=at_plain,
            refresh_token=rt_plain,
            expires_in=self.at_ttl,
            user=TokenUser(username=username, role=role),
        )

    # ── Validate access token ──────────────────────────────────────

    async def validate_access_token(self, plain_text: str) -> TokenUser | None:
        """验证 access token。成功则滑动续期，超过绝对上限返回 None 并撤销。"""
        if not plain_text or not plain_text.startswith("ccx_at_"):
            return None

        at_prefix = _first8_hex(plain_text)
        key = self._at_key(at_prefix)
        raw = await self._redis.hgetall(key)
        if not raw:
            return None

        # 完整 hash 碰撞检查
        stored_full = raw.get("token_full", "")
        if not hmac.compare_digest(stored_full.encode(), _full_hash(plain_text).encode()):
            return None

        if raw.get("revoked") == "1":
            return None

        now = int(time.time())
        expires_at = int(raw.get("expires_at", "0"))
        if now > expires_at:
            return None

        # 绝对过期检查
        created_at = int(raw.get("created_at", "0"))
        if (now - created_at) > self.at_absolute_lifetime:
            # 超过绝对上限 → 后台撤销整个 pair
            import asyncio
            asyncio.ensure_future(self._revoke_by_access_token_async(plain_text, at_prefix))
            return None

        # 滑动续期
        new_expires_at = now + self.at_ttl
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hset(key, "expires_at", str(new_expires_at))
            pipe.expire(key, self.at_ttl)
            await pipe.execute()

        return TokenUser(
            username=raw.get("username", ""),
            role=raw.get("role", "user"),
        )

    # ── Validate access token (只读，不续期) ───────────────────────

    async def user_from_access_token(self, plain_text: str) -> TokenUser | None:
        """只读获取 token 对应的用户，不续期。用于 /session 端点。"""
        if not plain_text or not plain_text.startswith("ccx_at_"):
            return None

        key = self._at_key(_first8_hex(plain_text))
        raw = await self._redis.hgetall(key)
        if not raw:
            return None

        if not hmac.compare_digest(
            raw.get("token_full", "").encode(),
            _full_hash(plain_text).encode(),
        ):
            return None

        if raw.get("revoked") == "1":
            return None

        if int(time.time()) > int(raw.get("expires_at", "0")):
            return None

        return TokenUser(
            username=raw.get("username", ""),
            role=raw.get("role", "user"),
        )

    # ── Refresh token pair ─────────────────────────────────────────

    async def refresh_token_pair(self, plain_text: str) -> TokenPair:
        """用 refresh token 换新 pair。旧 RT 立即撤销，旧 AT 保留 grace period。"""
        if not plain_text or not plain_text.startswith("ccx_rt_"):
            raise _AuthError("refresh token 格式无效")

        rt_prefix = _first8_hex(plain_text)
        key = self._rt_key(rt_prefix)
        raw = await self._redis.hgetall(key)
        if not raw:
            raise _AuthError("refresh token 无效或已过期")

        if not hmac.compare_digest(
            raw.get("token_full", "").encode(),
            _full_hash(plain_text).encode(),
        ):
            raise _AuthError("refresh token 无效或已过期")

        if raw.get("revoked") == "1":
            raise _AuthError("refresh token 已被撤销，请重新登录")

        if int(time.time()) > int(raw.get("expires_at", "0")):
            raise _AuthError("refresh token 已过期，请重新登录")

        username = raw.get("username", "")
        role = raw.get("role", "user")
        old_at_prefix = raw.get("at_prefix", "")

        # 旧 access token 延长 grace period (不直接撤销，保证途中的请求不被打断)
        if old_at_prefix:
            grace_expires_at = int(time.time()) + self.rt_grace
            old_at_key = self._at_key(old_at_prefix)
            async with self._redis.pipeline(transaction=True) as pipe:
                pipe.hset(old_at_key, "expires_at", str(grace_expires_at))
                pipe.expire(old_at_key, self.rt_grace)
                await pipe.execute()

        # 旧 refresh token 立即撤销
        await self._redis.hset(key, "revoked", "1")

        # 签发全新 pair
        return await self.issue_token_pair(username, role)

    # ── Revoke token pair ──────────────────────────────────────────

    async def revoke_token_pair(self, access_token: str) -> None:
        """撤销 access token 及其关联的 refresh token。"""
        if not access_token or not access_token.startswith("ccx_at_"):
            raise _AuthError("access token 格式无效")

        at_prefix = _first8_hex(access_token)
        await self._revoke_by_access_token_async(access_token, at_prefix)

    async def _revoke_by_access_token_async(self, plain_text: str, at_prefix: str) -> None:
        """后台撤销：验证 token 后同时标记 at 和关联的 rt 为 revoked=1。"""
        key = self._at_key(at_prefix)
        stored_full = await self._redis.hget(key, "token_full")
        if not stored_full:
            return

        if not hmac.compare_digest(
            stored_full.encode(),
            _full_hash(plain_text).encode(),
        ):
            return

        rt_prefix = await self._redis.hget(key, "rt_prefix")
        async with self._redis.pipeline(transaction=True) as pipe:
            pipe.hset(key, "revoked", "1")
            if rt_prefix:
                pipe.hset(self._rt_key(rt_prefix), "revoked", "1")
            await pipe.execute()

    # ── Force logout all devices ───────────────────────────────────

    async def revoke_all_user_tokens(self, username: str) -> int:
        """强制下线用户所有设备。返回被撤销的 token 数。"""
        count = 0
        for prefix in ("cc:at:", "cc:rt:"):
            cursor = 0
            while True:
                cursor, keys = await self._redis.scan(
                    cursor, match=f"{prefix}*", count=100
                )
                for key in keys:
                    raw = await self._redis.hgetall(key)
                    if raw.get("username") == username and raw.get("revoked") != "1":
                        await self._redis.hset(key, "revoked", "1")
                        count += 1
                if cursor == 0:
                    break
        return count


class _AuthError(Exception):
    """内部认证异常，统一映射为中文提示。"""
    pass
