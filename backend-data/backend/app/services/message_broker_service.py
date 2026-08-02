"""RabbitMQ 基础设施访问与 Redis 可靠消息租约。

RabbitMQ 连接、拓扑声明、发布和消费只能存在于 backend-data。其他服务
通过 backend-share/data-client 领取消息；消息在返回 HTTP 响应前先转存
Redis，并以可 ACK/NACK 的租约交付，避免把 MQ 客户端对象泄漏到服务边界外。

注意：本模块原有的 ``publish_inbound`` / ``claim_outbound`` / ``ack_outbound``
/ ``nack_outbound`` 4 个公开方法已删除（HTTP 消息代理端点废弃后无调用方）。
保留 ``ensure_topology`` / ``close`` 与若干 Redis 租约辅助方法，原因见
各方法 docstring。
"""

from __future__ import annotations

import asyncio
import re
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
    ValidationError,
)
from app.core.config import settings
from app.core.redis_client import RedisClientWrapper, get_redis_client

ROUTING_SEGMENT_PATTERN = re.compile(r"^[A-Za-z0-9_-]{1,64}$")


class MessageBrokerService:
    """集中管理 RabbitMQ 拓扑，并通过 Redis 租约向其他服务交付消息。

    保留原因：``app/core/business_observability.py`` 在 ``DATA_BUSINESS_SERVICES``
    中注册了本类用于结构化事件埋点；``app/main.py`` lifespan shutdown 调用
    ``close()`` 释放连接；``infrastructure.py`` 的 ``/topology`` 端点调用
    ``ensure_topology()``。删除本类会破坏上述 3 处依赖。
    """

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

    # ------------------------------------------------------------------
    # Redis 租约相关属性
    #
    # 保留原因：``_claim_from_relay`` 依赖这些 key 拼接 Redis 路径。虽然
    # ``claim_outbound`` 公开方法已删，但 ``_claim_from_relay`` 仍保留作为
    # Redis 可靠消息租约模式的参考实现，后续若重新引入基于 Redis 的
    # 出站消息租约（如 DLQ 兜底重试）可直接复用。
    # ------------------------------------------------------------------
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
        """建立 RabbitMQ 连接并幂等声明交换机、入站队列和出站队列。

        保留原因：``infrastructure.py`` 的 ``POST /message-broker/topology``
        端点调用本方法，``scripts/start-all.py`` 启动验证流程通过该端点
        触发 backend-data 自身初始化 MQ 拓扑。
        """
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

    async def close(self) -> None:
        """关闭 backend-data 持有的 RabbitMQ 连接。

        保留原因：``app/main.py`` lifespan shutdown 调用本方法释放连接，
        避免进程退出时连接泄漏。
        """
        async with self._connect_lock:
            connection = self._connection
            self._connection = None
            self._channel = None
            self._exchange = None
            self._outbound_queue = None
            if connection is not None and not connection.is_closed:
                await connection.close()

    def _claim_from_relay(self) -> dict[str, Any] | None:
        """从 Redis relay 队列领取一条消息（带租约）。

        保留原因：当前无调用方（原 ``claim_outbound`` 公开方法已删），
        但保留了完整的 Redis 可靠消息租约实现（ready/processing/attempts/
        dead-letter 四级流转），作为后续若重新引入基于 Redis 的出站消息
        兜底机制（如 DLQ 重试、限流退避）时的参考模板。
        """
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
        """校验 routing_key 片段格式。

        保留原因：当前无调用方（原 ``publish_inbound`` 公开方法已删），
        但保留了 routing_key 校验逻辑，作为后续若重新引入 HTTP 入站
        端点时的复用模板。
        """
        if not ROUTING_SEGMENT_PATTERN.fullmatch(value):
            raise ValidationError(
                message=(f"{field_name} 仅允许 1-64 位英文、数字、下划线和短横线")
            )

    @staticmethod
    def _message_header(
        headers: dict[str, Any] | None,
        name: str,
    ) -> str | None:
        """兼容 aio-pika 字符串或字节消息头。

        保留原因：当前无调用方（原 ``publish_inbound`` 公开方法已删），
        但保留了 aio-pika header 容错解析逻辑，作为后续若重新引入
        消息头处理逻辑时的复用模板。
        """
        if not headers:
            return None
        value = headers.get(name) or headers.get(name.lower())
        if isinstance(value, bytes):
            return value.decode("utf-8", errors="replace")
        return value if isinstance(value, str) else None


_message_broker_service: MessageBrokerService | None = None


def get_message_broker_service() -> MessageBrokerService:
    """获取 backend-data 进程内消息基础设施单例。"""
    global _message_broker_service
    if _message_broker_service is None:
        _message_broker_service = MessageBrokerService()
    return _message_broker_service
