"""RabbitMQ 基础设施访问与 Redis 可靠消息租约。

RabbitMQ 连接、拓扑声明、发布和消费只能存在于 backend-data。其他服务
通过 backend-share/data-client 领取消息；消息在返回 HTTP 响应前先转存
Redis，并以可 ACK/NACK 的租约交付，避免把 MQ 客户端对象泄漏到服务边界外。
"""

from __future__ import annotations

import asyncio
import re
import uuid
from datetime import UTC, datetime
from typing import Any

import aio_pika
from aio_pika.abc import (
    AbstractExchange,
    AbstractRobustChannel,
    AbstractRobustConnection,
    AbstractRobustQueue,
)
from api_common import (
    DependencyUnavailableError,
    ResourceNotFoundError,
    ValidationError,
)

from app.core.config import settings
from app.core.redis_client import RedisClientWrapper, get_redis_client


ROUTING_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class MessageBrokerService:
    """集中管理 RabbitMQ 拓扑，并通过 Redis 租约向其他服务交付消息。"""

    def __init__(
        self,
        redis_client: RedisClientWrapper | None = None,
    ) -> None:
        self._redis = redis_client or get_redis_client()
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractRobustChannel | None = None
        self._exchange: AbstractExchange | None = None
        self._outbound_queue: AbstractRobustQueue | None = None
        self._connect_lock = asyncio.Lock()

    @property
    def _ready_key(self) -> str:
        return f"{settings.message_relay_redis_prefix}:ready"

    @property
    def _processing_key(self) -> str:
        return f"{settings.message_relay_redis_prefix}:processing"

    @property
    def _attempts_key(self) -> str:
        return f"{settings.message_relay_redis_prefix}:attempts"

    @property
    def _dead_letter_key(self) -> str:
        return f"{settings.message_relay_redis_prefix}:dead-letter"

    @property
    def _message_key_prefix(self) -> str:
        return f"{settings.message_relay_redis_prefix}:message:"

    async def ensure_topology(self) -> dict[str, Any]:
        """建立 RabbitMQ 连接并幂等声明交换机、入站队列和出站队列。"""
        if self._is_ready():
            return self._topology_status()

        async with self._connect_lock:
            if self._is_ready():
                return self._topology_status()
            await self._reset_closed_handles()
            try:
                connection = await aio_pika.connect_robust(
                    settings.rabbitmq_url,
                )
                channel = await connection.channel(
                    publisher_confirms=True,
                )
                await channel.set_qos(
                    prefetch_count=settings.rabbitmq_prefetch_count,
                )
                exchange = await channel.declare_exchange(
                    settings.rabbitmq_exchange,
                    aio_pika.ExchangeType.TOPIC,
                    durable=True,
                )
                inbound_queue = await channel.declare_queue(
                    settings.rabbitmq_inbound_queue,
                    durable=True,
                )
                await inbound_queue.bind(
                    exchange,
                    routing_key=settings.rabbitmq_inbound_routing_key,
                )
                outbound_queue = await channel.declare_queue(
                    settings.rabbitmq_outbound_queue,
                    durable=True,
                )
                await outbound_queue.bind(
                    exchange,
                    routing_key=settings.rabbitmq_outbound_routing_key,
                )
            except Exception as exc:
                await self._reset_closed_handles()
                raise DependencyUnavailableError(
                    message="消息队列服务暂不可用",
                    detail=type(exc).__name__,
                ) from exc

            self._connection = connection
            self._channel = channel
            self._exchange = exchange
            self._outbound_queue = outbound_queue
            return self._topology_status()

    async def publish_inbound(
        self,
        *,
        platform: str,
        bot_id: str,
        payload: str,
    ) -> dict[str, str]:
        """把标准化入站消息持久化发布到 Agent 入站主题。"""
        self._validate_routing_segment(platform, field_name="platform")
        self._validate_routing_segment(bot_id, field_name="bot_id")
        await self.ensure_topology()
        if self._exchange is None:
            raise DependencyUnavailableError(message="消息队列尚未初始化")

        routing_key = f"{settings.rabbitmq_inbound_publish_prefix}.{platform}.{bot_id}"
        message_id = str(uuid.uuid4())
        try:
            await self._exchange.publish(
                aio_pika.Message(
                    body=payload.encode("utf-8"),
                    content_type="application/json",
                    delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
                    message_id=message_id,
                    timestamp=datetime.now(UTC),
                ),
                routing_key=routing_key,
            )
        except Exception as exc:
            raise DependencyUnavailableError(
                message="消息投递失败",
                detail=type(exc).__name__,
            ) from exc
        return {
            "message_id": message_id,
            "routing_key": routing_key,
        }

    async def claim_outbound(
        self,
        *,
        timeout_seconds: float,
    ) -> dict[str, Any] | None:
        """领取一条 Agent 出站消息，返回 Redis 租约回执。"""
        claimed = await asyncio.to_thread(self._claim_from_relay)
        if claimed is not None:
            return claimed

        await self.ensure_topology()
        if self._outbound_queue is None:
            raise DependencyUnavailableError(message="出站消息队列尚未初始化")

        try:
            incoming = await self._outbound_queue.get(
                fail=False,
                timeout=timeout_seconds,
            )
        except TimeoutError:
            return None
        except Exception as exc:
            raise DependencyUnavailableError(
                message="领取出站消息失败",
                detail=type(exc).__name__,
            ) from exc
        if incoming is None:
            return None

        receipt_id = str(uuid.uuid4())
        try:
            payload = incoming.body.decode("utf-8")
        except UnicodeDecodeError as exc:
            await incoming.reject(requeue=False)
            raise ValidationError(
                message="消息体必须使用 UTF-8 编码",
            ) from exc

        relay_payload = {
            "payload": payload,
            "routing_key": incoming.routing_key,
            "upstream_message_id": incoming.message_id,
            "received_at": datetime.now(UTC).isoformat(),
        }
        try:
            await asyncio.to_thread(
                self._redis.enqueue_relay_message,
                message_key=f"{self._message_key_prefix}{receipt_id}",
                ready_key=self._ready_key,
                receipt_id=receipt_id,
                payload=relay_payload,
                ttl_seconds=settings.message_relay_ttl_seconds,
            )
        except Exception:
            await incoming.nack(requeue=True)
            raise

        await incoming.ack()
        claimed = await asyncio.to_thread(self._claim_from_relay)
        if claimed is None:
            raise DependencyUnavailableError(
                message="消息已转存但暂时无法领取",
            )
        return claimed

    def ack_outbound(self, receipt_id: str) -> dict[str, str]:
        """确认消息已由网关成功处理。"""
        acknowledged = self._redis.ack_relay_message(
            receipt_id=receipt_id,
            processing_key=self._processing_key,
            attempts_key=self._attempts_key,
            message_key_prefix=self._message_key_prefix,
        )
        if not acknowledged:
            raise ResourceNotFoundError(
                message="消息回执不存在或租约已失效",
            )
        return {"receipt_id": receipt_id, "status": "acknowledged"}

    def nack_outbound(self, receipt_id: str) -> dict[str, str]:
        """处理失败时释放租约，使消息可以再次投递。"""
        released = self._redis.nack_relay_message(
            receipt_id=receipt_id,
            ready_key=self._ready_key,
            processing_key=self._processing_key,
            message_key_prefix=self._message_key_prefix,
        )
        if not released:
            raise ResourceNotFoundError(
                message="消息回执不存在或租约已失效",
            )
        return {"receipt_id": receipt_id, "status": "requeued"}

    async def close(self) -> None:
        """关闭 backend-data 持有的 RabbitMQ 连接。"""
        async with self._connect_lock:
            connection = self._connection
            self._connection = None
            self._channel = None
            self._exchange = None
            self._outbound_queue = None
            if connection is not None and not connection.is_closed:
                await connection.close()

    def _claim_from_relay(self) -> dict[str, Any] | None:
        return self._redis.claim_relay_message(
            ready_key=self._ready_key,
            processing_key=self._processing_key,
            attempts_key=self._attempts_key,
            dead_letter_key=self._dead_letter_key,
            message_key_prefix=self._message_key_prefix,
            lease_seconds=settings.message_lease_seconds,
            max_delivery_attempts=settings.message_max_delivery_attempts,
            dead_letter_limit=settings.message_dead_letter_limit,
        )

    def _is_ready(self) -> bool:
        return bool(
            self._connection is not None
            and not self._connection.is_closed
            and self._channel is not None
            and not self._channel.is_closed
            and self._exchange is not None
            and self._outbound_queue is not None
        )

    def _topology_status(self) -> dict[str, Any]:
        return {
            "connected": self._is_ready(),
            "exchange": settings.rabbitmq_exchange,
            "inbound_queue": settings.rabbitmq_inbound_queue,
            "outbound_queue": settings.rabbitmq_outbound_queue,
        }

    async def _reset_closed_handles(self) -> None:
        connection = self._connection
        self._connection = None
        self._channel = None
        self._exchange = None
        self._outbound_queue = None
        if connection is not None and not connection.is_closed:
            await connection.close()

    @staticmethod
    def _validate_routing_segment(value: str, *, field_name: str) -> None:
        if not ROUTING_SEGMENT_PATTERN.fullmatch(value):
            raise ValidationError(
                message=(f"{field_name} 仅允许 1-64 位英文、数字、下划线和短横线")
            )


_message_broker_service: MessageBrokerService | None = None


def get_message_broker_service() -> MessageBrokerService:
    """获取 backend-data 进程内消息基础设施单例。"""
    global _message_broker_service
    if _message_broker_service is None:
        _message_broker_service = MessageBrokerService()
    return _message_broker_service
