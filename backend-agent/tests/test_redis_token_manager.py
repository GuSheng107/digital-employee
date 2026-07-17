from __future__ import annotations

import unittest

from app.redis_token_manager import DualTokenManager


class _FakePipeline:
    def __init__(self, redis: "_FakeRedis") -> None:
        self._redis = redis
        self._ops = []

    async def __aenter__(self) -> "_FakePipeline":
        return self

    async def __aexit__(self, exc_type, exc, tb) -> None:
        return None

    def hset(self, key: str, field: str, value: str) -> None:
        self._ops.append(("hset", key, field, value))

    def expire(self, key: str, ttl: int) -> None:
        self._ops.append(("expire", key, ttl))

    def expireat(self, key: str, when: int) -> None:
        self._ops.append(("expireat", key, when))

    async def execute(self) -> None:
        for op in self._ops:
            if op[0] == "hset":
                _, key, field, value = op
                await self._redis.hset(key, field, value)
            elif op[0] == "expire":
                _, key, ttl = op
                self._redis.ttl[key] = int(ttl)
            elif op[0] == "expireat":
                _, key, when = op
                self._redis.expire_at[key] = int(when)


class _FakeRedis:
    def __init__(self) -> None:
        self.store: dict[str, dict[str, str]] = {}
        self.ttl: dict[str, int] = {}
        self.expire_at: dict[str, int] = {}

    def pipeline(self, transaction: bool = True) -> _FakePipeline:
        return _FakePipeline(self)

    async def hset(self, key: str, field: str, value: str) -> None:
        self.store.setdefault(key, {})[field] = str(value)

    async def hgetall(self, key: str) -> dict[str, str]:
        return dict(self.store.get(key, {}))

    async def hget(self, key: str, field: str) -> str | None:
        return self.store.get(key, {}).get(field)

    async def scan(self, cursor: int, match: str, count: int = 100):
        prefix = match.rstrip("*")
        keys = [key for key in self.store if key.startswith(prefix)]
        return 0, keys


class RedisTokenManagerTest(unittest.IsolatedAsyncioTestCase):
    async def test_validate_access_token_refreshes_expiry(self) -> None:
        fake = _FakeRedis()
        manager = DualTokenManager(fake, at_ttl_seconds=60, rt_ttl_seconds=3600)
        pair = await manager.issue_token_pair("alice", "admin")

        user = await manager.validate_access_token(pair.access_token)

        self.assertIsNotNone(user)
        at_key = next(key for key in fake.store if key.startswith("cc:at:"))
        self.assertEqual(fake.ttl[at_key], 60)
        self.assertEqual(fake.store[at_key]["username"], "alice")

    async def test_refresh_token_rotates_pair(self) -> None:
        fake = _FakeRedis()
        manager = DualTokenManager(fake, at_ttl_seconds=60, rt_ttl_seconds=3600)
        old_pair = await manager.issue_token_pair("alice", "admin")

        new_pair = await manager.refresh_token_pair(old_pair.refresh_token)

        self.assertNotEqual(old_pair.access_token, new_pair.access_token)
        self.assertNotEqual(old_pair.refresh_token, new_pair.refresh_token)
        revoked_rt = [
            data for key, data in fake.store.items()
            if key.startswith("cc:rt:") and data.get("revoked") == "1"
        ]
        self.assertEqual(len(revoked_rt), 1)

    async def test_revoked_access_token_is_rejected(self) -> None:
        fake = _FakeRedis()
        manager = DualTokenManager(fake, at_ttl_seconds=60, rt_ttl_seconds=3600)
        pair = await manager.issue_token_pair("alice", "admin")

        await manager.revoke_token_pair(pair.access_token)

        self.assertIsNone(await manager.validate_access_token(pair.access_token))


if __name__ == "__main__":
    unittest.main()
