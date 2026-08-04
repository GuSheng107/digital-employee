"""RabbitMQ 拓扑统一声明服务。

``backend-data`` 负责 RabbitMQ 拓扑的声明（Exchange、Queue、DLX/DLQ 的
创建与绑定），其他服务（如 ``backend-gateway`` 通过 ``backend-share/rabbitmq-client``
幂等 declare 获取本地引用）不自主声明拓扑。

与 ``backend-share/rabbitmq-client`` 使用同一套拓扑名称（通过 Nacos 环境变量
注入或代码默认值保持一致），确保各服务引用同一套 AMQP 拓扑结构。
"""

from __future__ import annotations

import asyncio
from typing import Any

import aio_pika
from aio_pika.abc import (
    AbstractExchange,
    AbstractRobustChannel,
    AbstractRobustConnection,
    AbstractRobustQueue,
)
from api_common import DependencyUnavailableError
from app.core.config import settings


class MessageBrokerService:
    """集中管理 RabbitMQ 拓扑的统一声明者。

    backend-data 作为 RabbitMQ 拓扑的权威声明者，在 lifespan 启动时
    调用 ``ensure_topology()`` 创建并绑定 Exchange、入站/出站队列及
    死信拓扑（DLX/DLQ），确保其他服务启动前拓扑已就绪。

    保留原因：
    - ``app/core/business_observability.py`` 在 ``DATA_BUSINESS_SERVICES``
      中注册了本类用于结构化事件埋点。
    - ``app/main.py`` lifespan shutdown 调用 ``close()`` 释放连接。
    - ``infrastructure.py`` 的 ``/topology`` 端点供 start-all.py 启动验证。
    """

    def __init__(self) -> None:
        self._connection: AbstractRobustConnection | None = None
        self._channel: AbstractRobustChannel | None = None
        self._exchange: AbstractExchange | None = None
        # 普通队列
        self._normal_inbound_queue: AbstractRobustQueue | None = None
        self._normal_outbound_queue: AbstractRobustQueue | None = None
        # VIP 队列
        self._vip_inbound_queue: AbstractRobustQueue | None = None
        self._vip_outbound_queue: AbstractRobustQueue | None = None
        # 普通死信
        self._dlx: AbstractExchange | None = None
        self._dlq_queue: AbstractRobustQueue | None = None
        # VIP 死信
        self._vip_dlx: AbstractExchange | None = None
        self._vip_dlq_queue: AbstractRobustQueue | None = None
        self._connect_lock = asyncio.Lock()

    async def ensure_topology(self) -> dict[str, Any]:
        """建立 RabbitMQ 连接并幂等声明全套拓扑（Exchange + Queue + DLX/DLQ）。

        拓扑结构：
        - ``digital_employee.events``（Topic Exchange，Durable）
          - ``normal_inbound_queue``，绑定 routing_key ``normal.inbound.message``
          - ``normal_outbound_queue``，绑定 routing_key ``normal.outbound.message``
          - ``vip_inbound_queue``，绑定 routing_key ``vip.inbound.message``
          - ``vip_outbound_queue``，绑定 routing_key ``vip.outbound.message``
        - ``digital_employee.dlx``（Direct Exchange，Durable，普通死信）
          - ``outbound_dlq``，绑定 routing_key ``normal.outbound.message``
        - ``digital_employee.vip.dlx``（Direct Exchange，Durable，VIP 死信）
          - ``vip_outbound_dlq``，绑定 routing_key ``vip.outbound.message``

        Returns:
            拓扑状态字典，包含 connected、exchange、dlx、dlq 等字段。
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

                # 声明主 Topic 交换机
                exchange = await channel.declare_exchange(
                    settings.rabbitmq_exchange,
                    aio_pika.ExchangeType.TOPIC,
                    durable=True,
                )

                # ── 普通入站队列 ──
                normal_inbound_queue = await channel.declare_queue(
                    settings.rabbitmq_normal_inbound_queue,
                    durable=True,
                )
                await normal_inbound_queue.bind(
                    exchange,
                    routing_key=settings.rabbitmq_normal_inbound_routing_key,
                )

                # ── 普通出站队列 ──
                normal_outbound_queue = await channel.declare_queue(
                    settings.rabbitmq_normal_outbound_queue,
                    durable=True,
                )
                await normal_outbound_queue.bind(
                    exchange,
                    routing_key=settings.rabbitmq_normal_outbound_routing_key,
                )

                # ── VIP 入站队列 ──
                vip_inbound_queue = await channel.declare_queue(
                    settings.rabbitmq_vip_inbound_queue,
                    durable=True,
                )
                await vip_inbound_queue.bind(
                    exchange,
                    routing_key=settings.rabbitmq_vip_inbound_routing_key,
                )

                # ── VIP 出站队列 ──
                vip_outbound_queue = await channel.declare_queue(
                    settings.rabbitmq_vip_outbound_queue,
                    durable=True,
                )
                await vip_outbound_queue.bind(
                    exchange,
                    routing_key=settings.rabbitmq_vip_outbound_routing_key,
                )

                # ── 普通死信拓扑：DLX (direct) + DLQ ──
                dlx = await channel.declare_exchange(
                    settings.rabbitmq_dlx,
                    aio_pika.ExchangeType.DIRECT,
                    durable=True,
                )
                dlq_queue = await channel.declare_queue(
                    settings.rabbitmq_dlq,
                    durable=True,
                )
                await dlq_queue.bind(
                    dlx,
                    routing_key=settings.rabbitmq_normal_outbound_routing_key,
                )

                # ── VIP 死信拓扑：独立 DLX (direct) + DLQ ──
                vip_dlx = await channel.declare_exchange(
                    settings.rabbitmq_vip_dlx,
                    aio_pika.ExchangeType.DIRECT,
                    durable=True,
                )
                vip_dlq_queue = await channel.declare_queue(
                    settings.rabbitmq_vip_dlq,
                    durable=True,
                )
                await vip_dlq_queue.bind(
                    vip_dlx,
                    routing_key=settings.rabbitmq_vip_outbound_routing_key,
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
            self._normal_inbound_queue = normal_inbound_queue
            self._normal_outbound_queue = normal_outbound_queue
            self._vip_inbound_queue = vip_inbound_queue
            self._vip_outbound_queue = vip_outbound_queue
            self._dlx = dlx
            self._dlq_queue = dlq_queue
            self._vip_dlx = vip_dlx
            self._vip_dlq_queue = vip_dlq_queue
            return self._topology_status()

    async def close(self) -> None:
        """关闭 backend-data 持有的 RabbitMQ 连接。

        在 ``app/main.py`` lifespan shutdown 时调用，避免进程退出时连接泄漏。
        """
        async with self._connect_lock:
            connection = self._connection
            self._connection = None
            self._channel = None
            self._exchange = None
            self._normal_inbound_queue = None
            self._normal_outbound_queue = None
            self._vip_inbound_queue = None
            self._vip_outbound_queue = None
            self._dlx = None
            self._dlq_queue = None
            self._vip_dlx = None
            self._vip_dlq_queue = None
            if connection is not None and not connection.is_closed:
                await connection.close()

    def _is_ready(self) -> bool:
        return bool(
            self._connection is not None
            and not self._connection.is_closed
            and self._channel is not None
            and not self._channel.is_closed
            and self._exchange is not None
            and self._normal_inbound_queue is not None
            and self._normal_outbound_queue is not None
            and self._vip_inbound_queue is not None
            and self._vip_outbound_queue is not None
            and self._dlx is not None
            and self._dlq_queue is not None
            and self._vip_dlx is not None
            and self._vip_dlq_queue is not None
        )

    def _topology_status(self) -> dict[str, Any]:
        return {
            "connected": self._is_ready(),
            "exchange": settings.rabbitmq_exchange,
            "normal_inbound_queue": settings.rabbitmq_normal_inbound_queue,
            "normal_outbound_queue": settings.rabbitmq_normal_outbound_queue,
            "vip_inbound_queue": settings.rabbitmq_vip_inbound_queue,
            "vip_outbound_queue": settings.rabbitmq_vip_outbound_queue,
            "dlx": settings.rabbitmq_dlx,
            "dlq": settings.rabbitmq_dlq,
            "vip_dlx": settings.rabbitmq_vip_dlx,
            "vip_dlq": settings.rabbitmq_vip_dlq,
        }

    async def _reset_closed_handles(self) -> None:
        connection = self._connection
        self._connection = None
        self._channel = None
        self._exchange = None
        self._normal_inbound_queue = None
        self._normal_outbound_queue = None
        self._vip_inbound_queue = None
        self._vip_outbound_queue = None
        self._dlx = None
        self._dlq_queue = None
        self._vip_dlx = None
        self._vip_dlq_queue = None
        if connection is not None and not connection.is_closed:
            await connection.close()


_message_broker_service: MessageBrokerService | None = None


def get_message_broker_service() -> MessageBrokerService:
    """获取 backend-data 进程内消息基础设施单例。"""
    global _message_broker_service
    if _message_broker_service is None:
        _message_broker_service = MessageBrokerService()
    return _message_broker_service

