"""邀请码服务：创建、查询。

邀请码存储在 Redis，key 为 ``invite_code:{code}``，
value 为 JSON ``{code, remaining, expires_at, created_by, created_at}``。
注册流程（见 AuthService.register）会消费邀请码：remaining -1，
归零后删除 key。
"""

from __future__ import annotations

import secrets
import string
import time

from app.core.redis_client import get_redis_client


class InviteCodeService:
    """邀请码管理服务。

    邀请码存储在 Redis，key 为 ``invite_code:{code}``，
    value 为 JSON ``{code, remaining, expires_at, created_by, created_at}``。
    TTL 与过期时间一致，过期后 Redis 自动清理，list_all 不会返回。
    """

    CODE_LENGTH = 8
    CODE_CHARS = string.ascii_uppercase + string.digits
    KEY_PREFIX = "invite_code:"

    def __init__(self) -> None:
        self._redis = get_redis_client()

    def create(
        self,
        *,
        remaining: int,
        expires_in_hours: int,
        created_by: int,
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
        code = self._generate_unique_code()
        now = time.time()
        ttl_seconds = expires_in_hours * 3600
        expires_at = now + ttl_seconds

        data = {
            "code": code,
            "remaining": remaining,
            "expires_at": expires_at,
            "created_by": created_by,
            "created_at": now,
        }
        key = f"{self.KEY_PREFIX}{code}"
        self._redis.set_json(key, data, ttl_seconds=ttl_seconds)

        return {
            "code": code,
            "remaining": remaining,
            "expires_at": expires_at,
            "expires_in": ttl_seconds,
        }

    def list_all(self) -> list[dict]:
        """列出所有邀请码，按创建时间倒序。

        已过期的 key 由 Redis TTL 自动清理；本方法额外依据 expires_at
        计算 is_valid，避免 TTL 与读取之间的竞态导致误判。
        """
        keys = self._redis.scan_keys(f"{self.KEY_PREFIX}*")
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

    def _generate_unique_code(self) -> str:
        """生成唯一的 8 位邀请码（大写字母 + 数字）。

        最多尝试 10 次；8 位字符空间约 2.8 万亿，碰撞概率极低，
        10 次仍冲突基本意味着 Redis 异常或 key 规范被破坏。
        """
        for _ in range(10):
            code = "".join(
                secrets.choice(self.CODE_CHARS) for _ in range(self.CODE_LENGTH)
            )
            key = f"{self.KEY_PREFIX}{code}"
            if self._redis.get(key) is None:
                return code
        raise RuntimeError("生成唯一邀请码失败, 请重试")
