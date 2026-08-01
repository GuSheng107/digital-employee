"""原生 RabbitMQ 异步 AMQP 客户端 (基于 aio-pika)。

提供连接管理、拓扑自动创建、网关消息发布与下行消息监听消费功能。
"""

from __future__ import annotations

import asyncio
import json
import os
from collections.abc import Awaitable, Callable
from typing import Any

import aio_pika
from loguru import logger
from observability import (
    TraceContext,
    bind_trace_context,
    current_trace_context,
    parse_uuid,
    reset_trace_context,
)

DEFAULT_RABBITMQ_URL = "amqp://guest:guest@127.0.0.1:5672/"
EXCHANGE_NAME = "digital_employee.events"
INBOUND_QUEUE_NAME = "inbound_queue"
OUTBOUND_QUEUE_NAME = "outbound_queue"
INBOUND_ROUTING_KEY = "inbound.message"
OUTBOUND_ROUTING_KEY = "outbound.message"


class RabbitMQClient:
    """基于 aio-pika 的原生 AMQP 异步收发客户端。"""

    def __init__(self, amqp_url: str | None = None) -> None:
        self.amqp_url = amqp_url or os.getenv("RABBITMQ_URL", DEFAULT_RABBITMQ_URL)
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None
        self._exchange: aio_pika.RobustExchange | None = None
        self._inbound_queue: aio_pika.RobustQueue | None = None
        self._outbound_queue: aio_pika.RobustQueue | None = None
        self.is_available: bool = False

    async def connect(self) -> None:
        """建立异步 AMQP Robust 连接与 Channel。"""
        if self._connection is not None and not self._connection.is_closed:
            return
        try:
            self._connection = await aio_pika.connect_robust(self.amqp_url)
            self._channel = await self._connection.channel()
            self.is_available = True
            logger.info("[RABBITMQ-CLIENT] 成功建立 RabbitMQ 异步连接")
        except Exception as exc:
            self.is_available = False
            logger.error("[RABBITMQ-CLIENT] RabbitMQ 连接建立失败: {}", exc)
            raise

    async def ensure_topology(self) -> dict[str, Any]:
        """建立并确认 RabbitMQ Exchange 与 Queue 拓扑。"""
        await self.connect()
        assert self._channel is not None

        # 声明 Topic 交换机
        self._exchange = await self._channel.declare_exchange(
            EXCHANGE_NAME,
            type=aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        # 声明并绑定入站与出站队列
        self._inbound_queue = await self._channel.declare_queue(
            INBOUND_QUEUE_NAME,
            durable=True,
        )
        await self._inbound_queue.bind(self._exchange, routing_key=INBOUND_ROUTING_KEY)

        self._outbound_queue = await self._channel.declare_queue(
            OUTBOUND_QUEUE_NAME,
            durable=True,
        )
        await self._outbound_queue.bind(self._exchange, routing_key=OUTBOUND_ROUTING_KEY)

        self.is_available = True
        logger.info("[RABBITMQ-CLIENT] 消息拓扑建立成功 ({})", EXCHANGE_NAME)
        return {"connected": True, "exchange": EXCHANGE_NAME}

    async def publish_inbound(
        self,
        *,
        platform: str,
        bot_id: str,
        payload: str,
    ) -> dict[str, Any]:
        """将网关上行消息直接发布至 RabbitMQ 入站队列。"""
        await self.connect()
        if self._exchange is None:
            await self.ensure_topology()
        assert self._exchange is not None

        current_ctx = current_trace_context()
        message_body = {
            "platform": platform,
            "bot_id": bot_id,
            "payload": payload,
            "trace_id": str(current_ctx.trace_id) if current_ctx else None,
            "parent_span_id": str(current_ctx.span_id) if current_ctx else None,
        }

        amqp_message = aio_pika.Message(
            body=json.dumps(message_body, ensure_ascii=False).encode("utf-8"),
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type="application/json",
            headers={
                "X-Trace-Id": str(current_ctx.trace_id) if current_ctx else "",
                "X-Span-Id": str(current_ctx.span_id) if current_ctx else "",
            },
        )

        await self._exchange.publish(amqp_message, routing_key=INBOUND_ROUTING_KEY)
        self.is_available = True
        return {"status": "published", "routing_key": INBOUND_ROUTING_KEY}

    async def start_outbound_consumer(
        self,
        callback: Callable[[str], Awaitable[bool]],
    ) -> None:
        """持续消费出站队列；根据回调执行结果进行自动 ACK/NACK。

        Args:
            callback: 消费回调，入参为字符串 Payload。返回 True 执行 ACK，返回 False 执行 NACK。
        """
        await self.connect()
        if self._outbound_queue is None:
            await self.ensure_topology()
        assert self._outbound_queue is not None

        logger.info("[RABBITMQ-CLIENT] 启动出站消息 AMQP 监听消费者...")

        async with self._outbound_queue.iterator() as queue_iter:
            async for message in queue_iter:
                async with message.process(requeue=True, ignore_processed=True):
                    trace_token = None
                    try:
                        raw_body = message.body.decode("utf-8")
                        body_json = json.loads(raw_body)
                        payload = body_json.get("payload", raw_body)

                        # 提取 Trace Context
                        trace_id = parse_uuid(body_json.get("trace_id") or message.headers.get("X-Trace-Id"))
                        parent_span = parse_uuid(body_json.get("parent_span_id") or message.headers.get("X-Span-Id"))
                        if trace_id and parent_span:
                            trace_token = bind_trace_context(
                                TraceContext(trace_id=trace_id, span_id=parent_span)
                            )

                        success = await callback(payload)
                        if success:
                            await message.ack()
                        else:
                            await message.nack(requeue=True)
                    except Exception as exc:
                        logger.exception("[RABBITMQ-CLIENT] 处理出站消息异常: {}", exc)
                        await message.nack(requeue=True)
                    finally:
                        if trace_token is not None:
                            reset_trace_context(trace_token)

    async def close(self) -> None:
        """关闭 AMQP 连接。"""
        self.is_available = False
        if self._connection is not None and not self._connection.is_closed:
            await self._connection.close()
            self._connection = None
            self._channel = None
            logger.info("[RABBITMQ-CLIENT] RabbitMQ 连接已关闭")


_global_rabbitmq_client: RabbitMQClient | None = None


def get_rabbitmq_client() -> RabbitMQClient:
    """获取全局单例 RabbitMQClient。"""
    global _global_rabbitmq_client
    if _global_rabbitmq_client is None:
        _global_rabbitmq_client = RabbitMQClient()
    return _global_rabbitmq_client
