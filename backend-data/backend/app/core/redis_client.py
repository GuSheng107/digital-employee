from __future__ import annotations

import json
import secrets
import time
from threading import Lock
from typing import Any

from redis import Redis
from redis.exceptions import ResponseError, WatchError

from app.core.config import settings


class RedisClientWrapper:
    """Centralized Redis wrapper for cache primitives used by services."""

    LOCK_TTL_SECONDS = 10
    LOCK_WAIT_SECONDS = 3.0
    LOCK_RETRY_INTERVAL_SECONDS = 0.02

    def __init__(self) -> None:
        self.redis_url = settings.redis_url
        self.client: Redis | None = None
        self._init_lock = Lock()

    def init_client(self) -> None:
        if self.client is not None:
            return
        with self._init_lock:
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

    def delete(self, *keys: str) -> int:
        """删除一个或多个 key。"""
        if not keys:
            return 0
        return int(self._require_client().delete(*keys))

    def sadd(self, key: str, *members: str) -> int:
        """向集合添加成员。"""
        return int(self._require_client().sadd(key, *members))

    def srem(self, key: str, *members: str) -> int:
        """从集合移除成员。"""
        return int(self._require_client().srem(key, *members))

    def smembers(self, key: str) -> set[str]:
        """读取集合全部成员。"""
        return set(self._require_client().smembers(key))

    def expire(self, key: str, ttl_seconds: int) -> bool:
        """设置 key 的过期时间。"""
        return bool(self._require_client().expire(key, ttl_seconds))

    def increment_with_ttl(self, key: str, *, ttl_seconds: int) -> int:
        """在固定时间窗内原子递增计数并确保 TTL 存在。"""
        client = self._require_client()
        while True:
            with client.pipeline() as pipeline:
                try:
                    pipeline.watch(key)
                    current_value = pipeline.get(key)
                    next_value = int(current_value) + 1 if current_value else 1
                    remaining_ttl = int(pipeline.ttl(key)) if current_value else -1
                    pipeline.multi()
                    pipeline.set(
                        key,
                        next_value,
                        ex=remaining_ttl if remaining_ttl > 0 else ttl_seconds,
                    )
                    pipeline.execute()
                    return next_value
                except WatchError:
                    continue

    def scan_keys(self, pattern: str) -> list[str]:
        """使用 SCAN 增量读取匹配 key，避免 KEYS 阻塞 Redis。"""
        client = self._require_client()
        keys: list[str] = []
        cursor = 0
        while True:
            cursor, batch = client.scan(
                cursor=cursor,
                match=pattern,
                count=100,
            )
            keys.extend(str(key) for key in batch)
            if cursor == 0:
                break
        return keys

    def replace_user_token_pair(
        self,
        *,
        user_tokens_key: str,
        access_key: str,
        refresh_key: str,
        pair_key: str,
        access_key_prefix: str,
        refresh_key_prefix: str,
        pair_key_prefix: str,
        replaced_access_key_prefix: str,
        user_id: int,
        access_token: str,
        refresh_token: str,
        access_ttl_seconds: int,
        refresh_ttl_seconds: int,
    ) -> None:
        """撤销旧会话并签发唯一的新 token 对。

        当前会话由 ``user_tokens_key`` 这一单键 JSON 作为线性化点；所有
        token 映射先写入，最后一次 ``SET`` 切换当前会话。即使历史映射仍在
        TTL 内，读取时也必须匹配当前会话，因此旧客户端会立即失效。
        """
        client = self._require_client()
        lock_key = f"{user_tokens_key}:lock"
        lock_token = self._acquire_lock(client, lock_key)
        try:
            old_pair = self._read_session_marker(client, user_tokens_key)
            client.set(
                access_key,
                user_id,
                ex=access_ttl_seconds,
            )
            client.set(
                refresh_key,
                user_id,
                ex=refresh_ttl_seconds,
            )
            client.set(
                pair_key,
                access_token,
                ex=refresh_ttl_seconds,
            )
            client.set(
                user_tokens_key,
                self._serialize_session_marker(
                    access_token=access_token,
                    refresh_token=refresh_token,
                ),
                ex=refresh_ttl_seconds,
            )

            if old_pair:
                client.set(
                    f"{replaced_access_key_prefix}{old_pair['access_token']}",
                    "1",
                    ex=access_ttl_seconds,
                )
                obsolete_keys = (
                    f"{access_key_prefix}{old_pair['access_token']}",
                    f"{refresh_key_prefix}{old_pair['refresh_token']}",
                    f"{pair_key_prefix}{old_pair['refresh_token']}",
                )
                keys_to_delete = [
                    key
                    for key in obsolete_keys
                    if key not in {access_key, refresh_key, pair_key}
                ]
                if keys_to_delete:
                    client.delete(*keys_to_delete)
        finally:
            self._release_lock(client, lock_key, lock_token)

    def rotate_user_token_pair(
        self,
        *,
        old_refresh_key: str,
        old_pair_key: str,
        user_tokens_key: str,
        new_access_key: str,
        new_refresh_key: str,
        new_pair_key: str,
        access_key_prefix: str,
        expected_user_id: int,
        old_refresh_token: str,
        new_access_token: str,
        new_refresh_token: str,
        access_ttl_seconds: int,
        refresh_ttl_seconds: int,
    ) -> bool:
        """消费一次性 refresh token 并写入新 token 对。

        ``SET NX`` 的 claim key 保证 refresh token 只能被一个并发请求消费；
        用户级短租约锁与单键会话标记保证登录、刷新、撤销互相串行。
        """
        client = self._require_client()
        lock_key = f"{user_tokens_key}:lock"
        lock_token = self._acquire_lock(client, lock_key)
        try:
            stored_user_id = client.get(old_refresh_key)
            current_pair = self._read_session_marker(client, user_tokens_key)
            if (
                stored_user_id is None
                or int(stored_user_id) != expected_user_id
                or current_pair is None
                or current_pair["refresh_token"] != old_refresh_token
            ):
                return False

            claimed = client.set(
                f"{old_refresh_key}:claimed",
                "1",
                ex=refresh_ttl_seconds,
                nx=True,
            )
            if not claimed:
                return False

            old_access_token = current_pair["access_token"]
            client.set(
                new_access_key,
                expected_user_id,
                ex=access_ttl_seconds,
            )
            client.set(
                new_refresh_key,
                expected_user_id,
                ex=refresh_ttl_seconds,
            )
            client.set(
                new_pair_key,
                new_access_token,
                ex=refresh_ttl_seconds,
            )
            client.set(
                user_tokens_key,
                self._serialize_session_marker(
                    access_token=new_access_token,
                    refresh_token=new_refresh_token,
                ),
                ex=refresh_ttl_seconds,
            )
            client.delete(
                old_refresh_key,
                old_pair_key,
                f"{access_key_prefix}{old_access_token}",
            )
            return True
        finally:
            self._release_lock(client, lock_key, lock_token)

    def revoke_user_token_pair(
        self,
        *,
        user_tokens_key: str,
        access_key_prefix: str,
        refresh_key_prefix: str,
        pair_key_prefix: str,
    ) -> None:
        """撤销用户当前 token 对；旧映射即使短暂残留也无法通过会话校验。"""
        client = self._require_client()
        lock_key = f"{user_tokens_key}:lock"
        lock_token = self._acquire_lock(client, lock_key)
        try:
            current_pair = self._read_session_marker(client, user_tokens_key)
            client.delete(user_tokens_key)
            if current_pair:
                client.delete(
                    f"{access_key_prefix}{current_pair['access_token']}",
                    f"{refresh_key_prefix}{current_pair['refresh_token']}",
                    f"{pair_key_prefix}{current_pair['refresh_token']}",
                )
        finally:
            self._release_lock(client, lock_key, lock_token)

    def read_user_token_pair(
        self,
        user_tokens_key: str,
    ) -> dict[str, str] | None:
        """读取用户当前会话的 access/refresh token 标记。"""
        return self._read_session_marker(
            self._require_client(),
            user_tokens_key,
        )

    def exists(self, key: str) -> bool:
        """判断指定 key 是否存在。"""
        return bool(self._require_client().exists(key))

    def set_json(
        self,
        key: str,
        value: Any,
        *,
        ttl_seconds: int | None = None,
    ) -> bool:
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return self.set(key, payload, ttl_seconds=ttl_seconds)

    def set_json_if_absent(
        self,
        key: str,
        value: Any,
        *,
        ttl_seconds: int,
    ) -> bool:
        """仅在 key 不存在时原子写入 JSON 与 TTL。"""
        payload = json.dumps(value, ensure_ascii=False, separators=(",", ":"))
        return bool(
            self._require_client().set(
                key,
                payload,
                ex=ttl_seconds,
                nx=True,
            )
        )

    def get_json(self, key: str) -> Any:
        value = self.get(key)
        if value is None:
            return None
        return json.loads(value)

    def consume_json_counter(
        self,
        key: str,
        *,
        counter_field: str,
    ) -> dict[str, Any] | None:
        """原子递减 JSON 对象中的计数字段。

        通过最小权限 Redis 账号可用的 ``SET NX`` 短租约锁串行化消费，
        防止并发注册超额使用同一邀请码；计数归零时保留 key 到原 TTL，
        以便数据库事务失败后执行补偿。
        """
        client = self._require_client()
        lock_key = f"{key}:lock"
        lock_token = self._acquire_lock(client, lock_key)
        try:
            raw = client.get(key)
            if raw is None:
                return None
            data = json.loads(str(raw))
            if not isinstance(data, dict):
                return None
            remaining = int(data.get(counter_field, 0))
            if remaining <= 0:
                return None
            data[counter_field] = remaining - 1
            ttl_seconds = int(client.ttl(key))
            if ttl_seconds > 0:
                client.set(
                    key,
                    json.dumps(
                        data,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                    ex=ttl_seconds,
                )
            else:
                client.set(
                    key,
                    json.dumps(
                        data,
                        ensure_ascii=False,
                        separators=(",", ":"),
                    ),
                )
            return data
        finally:
            self._release_lock(client, lock_key, lock_token)

    def restore_json_counter(
        self,
        key: str,
        *,
        counter_field: str,
    ) -> None:
        """补回一次已消费的 JSON 计数，保持原有 TTL。"""
        client = self._require_client()
        lock_key = f"{key}:lock"
        lock_token = self._acquire_lock(client, lock_key)
        try:
            raw = client.get(key)
            if raw is None:
                raise RuntimeError("counter no longer exists")
            data = json.loads(str(raw))
            if not isinstance(data, dict):
                raise RuntimeError("counter payload is invalid")
            data[counter_field] = int(data.get(counter_field, 0)) + 1
            ttl_seconds = int(client.ttl(key))
            serialized = json.dumps(
                data,
                ensure_ascii=False,
                separators=(",", ":"),
            )
            if ttl_seconds > 0:
                client.set(key, serialized, ex=ttl_seconds)
            else:
                client.set(key, serialized)
        finally:
            self._release_lock(client, lock_key, lock_token)

    def enqueue_relay_message(
        self,
        *,
        message_key: str,
        ready_key: str,
        receipt_id: str,
        payload: dict[str, Any],
        ttl_seconds: int,
    ) -> bool:
        """把已从 MQ 接收的消息可靠转存到 Redis 待处理队列。"""
        serialized = json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
        )
        client = self._require_client()
        lock_key = self._relay_lock_key(ready_key)
        lock_token = self._acquire_lock(client, lock_key)
        try:
            created = client.set(
                message_key,
                serialized,
                ex=ttl_seconds,
                nx=True,
            )
            if not created:
                return False
            try:
                client.lpush(ready_key, receipt_id)
            except Exception:
                client.delete(message_key)
                raise
            return True
        finally:
            self._release_lock(client, lock_key, lock_token)

    def claim_relay_message(
        self,
        *,
        ready_key: str,
        processing_key: str,
        attempts_key: str,
        dead_letter_key: str,
        message_key_prefix: str,
        lease_seconds: int,
        max_delivery_attempts: int,
        dead_letter_limit: int,
    ) -> dict[str, Any] | None:
        """串行领取一条消息，并回收租约已过期的消息。

        领取使用 Redis 租约而不是进程内 ``IncomingMessage``，因此
        backend-data 多进程部署或请求落到不同实例时仍可完成 ACK/NACK。
        超过最大投递次数的消息进入有界死信列表，避免无限重试。
        """
        client = self._require_client()
        lock_key = self._relay_lock_key(ready_key)
        lock_token = self._acquire_lock(client, lock_key)
        try:
            now = time.time()
            expired_receipt_ids = [
                str(receipt_id)
                for receipt_id in client.zrangebyscore(
                    processing_key,
                    "-inf",
                    now,
                    start=0,
                    num=100,
                )
            ]
            for receipt_id in expired_receipt_ids:
                client.zrem(processing_key, receipt_id)
                if client.exists(f"{message_key_prefix}{receipt_id}"):
                    client.lpush(ready_key, receipt_id)

            for _ in range(100):
                receipt_value = client.lindex(ready_key, -1)
                if receipt_value is None:
                    return None
                receipt_id = str(receipt_value)
                if client.zscore(processing_key, receipt_id) is not None:
                    client.rpop(ready_key)
                    continue
                message_key = f"{message_key_prefix}{receipt_id}"
                raw_value = client.get(message_key)
                if raw_value is None:
                    client.rpop(ready_key)
                    client.hdel(attempts_key, receipt_id)
                    continue

                # 先建立短租约再从 ready 队列移除；进程若在两步之间退出，
                # 下一次领取会跳过重复 ready 项，租约到期后再安全回收。
                client.zadd(
                    processing_key,
                    {receipt_id: time.time() + lease_seconds},
                )
                popped = client.rpop(ready_key)
                if popped is None or str(popped) != receipt_id:
                    client.zrem(processing_key, receipt_id)
                    raise RuntimeError("Redis relay ready queue changed unexpectedly")

                delivery_attempt = int(
                    client.hincrby(attempts_key, receipt_id, 1)
                )
                raw = str(raw_value)
                if delivery_attempt > max_delivery_attempts:
                    client.zrem(processing_key, receipt_id)
                    client.lpush(dead_letter_key, raw)
                    client.ltrim(dead_letter_key, 0, dead_letter_limit - 1)
                    client.delete(message_key)
                    client.hdel(attempts_key, receipt_id)
                    continue

                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = None
                if not isinstance(data, dict):
                    client.zrem(processing_key, receipt_id)
                    client.hdel(attempts_key, receipt_id)
                    client.delete(message_key)
                    continue
                data["receipt_id"] = receipt_id
                data["delivery_attempt"] = delivery_attempt
                return data
            return None
        finally:
            self._release_lock(client, lock_key, lock_token)

    def ack_relay_message(
        self,
        *,
        receipt_id: str,
        processing_key: str,
        attempts_key: str,
        message_key_prefix: str,
    ) -> bool:
        """确认消息处理成功并清理 Redis 中的租约与消息体。"""
        client = self._require_client()
        message_key = f"{message_key_prefix}{receipt_id}"
        lock_key = self._relay_lock_key(processing_key)
        lock_token = self._acquire_lock(client, lock_key)
        try:
            was_processing = client.zrem(processing_key, receipt_id) > 0
            client.hdel(attempts_key, receipt_id)
            client.delete(message_key)
            return was_processing
        finally:
            self._release_lock(client, lock_key, lock_token)

    def nack_relay_message(
        self,
        *,
        receipt_id: str,
        ready_key: str,
        processing_key: str,
        message_key_prefix: str,
    ) -> bool:
        """释放消息租约并重新放回待处理队列。"""
        client = self._require_client()
        message_key = f"{message_key_prefix}{receipt_id}"
        lock_key = self._relay_lock_key(ready_key)
        lock_token = self._acquire_lock(client, lock_key)
        try:
            if (
                client.zscore(processing_key, receipt_id) is None
                or not client.exists(message_key)
            ):
                return False
            client.zrem(processing_key, receipt_id)
            client.lpush(ready_key, receipt_id)
            return True
        finally:
            self._release_lock(client, lock_key, lock_token)

    @staticmethod
    def _serialize_session_marker(
        *,
        access_token: str,
        refresh_token: str,
    ) -> str:
        return json.dumps(
            {
                "access_token": access_token,
                "refresh_token": refresh_token,
            },
            ensure_ascii=False,
            separators=(",", ":"),
        )

    @staticmethod
    def _read_session_marker(
        client: Redis,
        user_tokens_key: str,
    ) -> dict[str, str] | None:
        """读取单键会话标记；旧版 Set 类型按无会话处理并由下次登录覆盖。"""
        try:
            raw = client.get(user_tokens_key)
        except ResponseError:
            return None
        if raw is None:
            return None
        try:
            data = json.loads(str(raw))
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict):
            return None
        access_token = data.get("access_token")
        refresh_token = data.get("refresh_token")
        if not isinstance(access_token, str) or not isinstance(refresh_token, str):
            return None
        return {
            "access_token": access_token,
            "refresh_token": refresh_token,
        }

    def _acquire_lock(
        self,
        client: Redis,
        lock_key: str,
    ) -> str:
        """使用 ``SET NX EX`` 获取短租约锁，兼容禁用脚本/事务的 Redis ACL。"""
        lock_token = secrets.token_urlsafe(18)
        deadline = time.monotonic() + self.LOCK_WAIT_SECONDS
        while time.monotonic() < deadline:
            if client.set(
                lock_key,
                lock_token,
                nx=True,
                ex=self.LOCK_TTL_SECONDS,
            ):
                return lock_token
            time.sleep(self.LOCK_RETRY_INTERVAL_SECONDS)
        raise RuntimeError(f"Redis lock acquisition timed out: {lock_key}")

    @staticmethod
    def _release_lock(
        client: Redis,
        lock_key: str,
        lock_token: str,
    ) -> None:
        """使用 WATCH/MULTI 原子释放仍属于当前调用方的短租约锁。"""
        while True:
            with client.pipeline() as pipeline:
                try:
                    pipeline.watch(lock_key)
                    if pipeline.get(lock_key) != lock_token:
                        pipeline.unwatch()
                        return
                    pipeline.multi()
                    pipeline.delete(lock_key)
                    pipeline.execute()
                    return
                except WatchError:
                    continue

    @staticmethod
    def _relay_lock_key(relay_key: str) -> str:
        """从 ``prefix:ready/processing`` 派生同一个消息租约锁 key。"""
        prefix, separator, _ = relay_key.rpartition(":")
        return f"{prefix}:lock" if separator else f"{relay_key}:lock"

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
