"""backend-data 内部邀请码存储服务。

邀请码存储在 Redis，key 为 ``invite_code:{code}``，
value 为 JSON ``{code, remaining, expires_at, created_by, created_at}``。
注册流程（见 AuthService.register）会消费邀请码：remaining -1，
归零后保留至原 TTL，以便数据库事务失败时补回次数。
"""

from __future__ import annotations

import secrets
import string
import time

from api_common import (
    DuplicateResourceError,
    InvalidCredentialsError,
)
from auth_utils import INVITE_CODE_GENERATED_LENGTH

from app.core.config import settings
from app.core.redis_client import get_redis_client


class InviteCodeService:
    """邀请码管理服务。

    邀请码存储在 Redis，key 为 ``invite_code:{code}``，
    value 为 JSON ``{code, remaining, expires_at, created_by, created_at}``。
    TTL 与过期时间一致，过期后 Redis 自动清理，list_all 不会返回。
    """

    CODE_CHARS = string.ascii_uppercase + string.digits
    MAX_GENERATION_ATTEMPTS = 10

    def __init__(self) -> None:
        self._redis = get_redis_client()
        self._key_prefix = f"{settings.invite_code_redis_prefix}:"

    def create(
        self,
        *,
        remaining: int,
        expires_in_hours: int,
        created_by: int,
        custom_code: str | None = None,
    ) -> dict:
        """创建邀请码。

        Args:
            remaining: 可用次数（1-100）。
            expires_in_hours: 过期时间（小时），TTL 据此设置。
            created_by: 创建者 user_id。

        Returns:
            包含 code、remaining、expires_at、expires_in 的字典。

        Raises:
            RuntimeError: 10 次尝试仍生成不了唯一邀请码。
        """
        now = time.time()
        ttl_seconds = expires_in_hours * 3600
        expires_at = now + ttl_seconds
        for _ in range(self.MAX_GENERATION_ATTEMPTS):
            code = custom_code or self._generate_code()
            data = {
                "code": code,
                "remaining": remaining,
                "expires_at": expires_at,
                "created_by": created_by,
                "created_at": now,
            }
            created = self._redis.set_json_if_absent(
                self._key(code),
                data,
                ttl_seconds=ttl_seconds,
            )
            if created:
                return {
                    "code": code,
                    "remaining": remaining,
                    "expires_at": expires_at,
                    "expires_in": ttl_seconds,
                }
            if custom_code:
                raise DuplicateResourceError(message="邀请码已存在")
        raise RuntimeError("生成唯一邀请码失败，请重试")

    def list_all(self) -> list[dict]:
        """列出所有邀请码，按创建时间倒序。

        已过期的 key 由 Redis TTL 自动清理；本方法额外依据 expires_at
        计算 is_valid，避免 TTL 与读取之间的竞态导致误判。
        """
        keys = self._redis.scan_keys(f"{self._key_prefix}*")
        items: list[dict] = []
        now = time.time()
        for key in keys:
            data = self._redis.get_json(key)
            if data is None:
                continue
            remaining = int(data.get("remaining", 0))
            expires_at = float(data.get("expires_at", 0))
            is_valid = remaining > 0 and expires_at > now
            items.append(
                {
                    "code": data.get("code", ""),
                    "remaining": remaining,
                    "expires_at": expires_at,
                    "created_by": int(data.get("created_by", 0)),
                    "created_at": float(data.get("created_at", 0)),
                    "is_valid": is_valid,
                }
            )
        items.sort(key=lambda x: x["created_at"], reverse=True)
        return items

    def list_page(self, *, page: int, page_size: int) -> dict:
        """分页返回邀请码列表。"""
        items = self.list_all()
        start = (page - 1) * page_size
        return {
            "items": items[start : start + page_size],
            "total": len(items),
            "page": page,
            "page_size": page_size,
        }

    def consume(self, code: str) -> None:
        """原子消费一次邀请码。"""
        updated = self._redis.consume_json_counter(
            self._key(code),
            counter_field="remaining",
        )
        if updated is None:
            raise InvalidCredentialsError(message="邀请码无效或已用完")

    def restore(self, code: str) -> None:
        """在注册事务失败时补回邀请码次数。"""
        self._redis.restore_json_counter(
            self._key(code),
            counter_field="remaining",
        )

    def _generate_code(self) -> str:
        """生成 8 位随机候选邀请码，唯一性由 Redis ``SET NX`` 保证。"""
        return "".join(
            secrets.choice(self.CODE_CHARS) for _ in range(INVITE_CODE_GENERATED_LENGTH)
        )

    def _key(self, code: str) -> str:
        """构造邀请码 Redis key。"""
        return f"{self._key_prefix}{code}"
