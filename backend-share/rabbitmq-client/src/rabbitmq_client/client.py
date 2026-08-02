"""原生 RabbitMQ 异步 AMQP 客户端 (基于 aio-pika)。

提供连接管理、拓扑自动创建、网关消息发布与下行消息监听消费功能。
"""

from __future__ import annotations

import asyncio
import enum
import json
import os
from collections.abc import Awaitable, Callable, Mapping
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
# 以下拓扑名称从 Nacos 配置（经环境变量注入）读取，backend-data 为统一声明者。
# share 包通过幂等 declare 获取本地引用，不自主声明拓扑。
EXCHANGE_NAME = os.getenv("RABBITMQ_EXCHANGE", "digital_employee.events")
INBOUND_QUEUE_NAME = os.getenv("RABBITMQ_INBOUND_QUEUE", "inbound_queue")
OUTBOUND_QUEUE_NAME = os.getenv("RABBITMQ_OUTBOUND_QUEUE", "outbound_queue")
INBOUND_ROUTING_KEY = os.getenv("RABBITMQ_INBOUND_ROUTING_KEY", "inbound.message")
OUTBOUND_ROUTING_KEY = os.getenv("RABBITMQ_OUTBOUND_ROUTING_KEY", "outbound.message")

# 死信拓扑：DLX 采用 direct 类型，DLQ 与 outbound_queue 同 routing_key 绑定。
# 消费者手动控制 ACK/RETRY/DLQ 三态，不依赖队列级 x-dead-letter-exchange 自动转投，
# 便于在死信消息中附加原因、保留原始 retry_count。
DLX_NAME = os.getenv("RABBITMQ_DLX", "digital_employee.dlx")
DLQ_NAME = os.getenv("RABBITMQ_DLQ", "outbound_dlq")
DLQ_ROUTING_KEY = OUTBOUND_ROUTING_KEY

# 重试上限：超过后转发 DLQ。IM 平台瞬时故障通常几秒到几分钟恢复，5 次重试可覆盖大多数场景。
MAX_RETRY_COUNT = 5
RETRY_COUNT_HEADER = "x-retry-count"
DEAD_LETTER_REASON_HEADER = "x-dead-letter-reason"


class ConsumerResult(enum.Enum):
    """消费回调三态结果，决定 SDK 侧 ACK/RETRY/DLQ 路由。"""

    ACK = "ack"  # 处理成功，SDK 直接 ACK
    RETRY = "retry"  # 可重试失败（如 IM 平台抖动），SDK 递增 retry_count 后重发
    DLQ = "dlq"  # 不可重试失败（如消息格式错、Bot 缺失），SDK 直接转 DLQ


def _read_retry_count(headers: Mapping[str, Any] | None) -> int:
    """从消息 header 读取重试计数，缺省返回 0。

    aio-pika 的 ``message.headers`` 可能是 ``None`` 或字段类型不一致，
    本函数统一做容错解析。
    """
    if not headers:
        return 0
    value = headers.get(RETRY_COUNT_HEADER)
    if value is None:
        return 0
    try:
        return int(value)
    except (TypeError, ValueError):
        return 0


class RabbitMQClient:
    """基于 aio-pika 的原生 AMQP 异步收发客户端。"""

    def __init__(self, amqp_url: str | None = None) -> None:
        self.amqp_url = amqp_url or os.getenv("RABBITMQ_URL", DEFAULT_RABBITMQ_URL)
        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None
        self._exchange: aio_pika.RobustExchange | None = None
        self._dlx: aio_pika.RobustExchange | None = None
        self._inbound_queue: aio_pika.RobustQueue | None = None
        self._outbound_queue: aio_pika.RobustQueue | None = None
        self._dlq_queue: aio_pika.RobustQueue | None = None
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

        # 声明死信拓扑：DLX (direct) + DLQ，与 outbound_queue 共用 routing_key。
        # 消费者手动控制 DLQ 路由（见 start_outbound_consumer），不依赖队列级
        # x-dead-letter-exchange 自动转投，便于在死信消息中附加原因元信息。
        self._dlx = await self._channel.declare_exchange(
            DLX_NAME,
            type=aio_pika.ExchangeType.DIRECT,
            durable=True,
        )
        self._dlq_queue = await self._channel.declare_queue(
            DLQ_NAME,
            durable=True,
        )
        await self._dlq_queue.bind(self._dlx, routing_key=DLQ_ROUTING_KEY)

        self.is_available = True
        logger.info(
            "[RABBITMQ-CLIENT] 消息拓扑建立成功 (exchange={}, dlx={}, dlq={})",
            EXCHANGE_NAME,
            DLX_NAME,
            DLQ_NAME,
        )
        return {
            "connected": True,
            "exchange": EXCHANGE_NAME,
            "dlx": DLX_NAME,
            "dlq": DLQ_NAME,
        }

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
        callback: Callable[[str], Awaitable[ConsumerResult]],
    ) -> None:
        """持续消费出站队列；根据回调返回的 :class:`ConsumerResult` 路由消息。

        路由策略：
        - ``ACK``  → ``message.ack()``，消息出队
        - ``RETRY`` → 递增 ``x-retry-count`` header 后重新 publish 到原队列，
          随后 ``ack`` 原消息。重试次数超过 :data:`MAX_RETRY_COUNT` 时转 DLQ
        - ``DLQ``  → 转 DLQ 并 ``ack`` 原消息
        - 回调抛异常 → 视为不可重试失败，转 DLQ 并 ``ack`` 原消息，避免无限重试

        不使用 ``message.process()`` 上下文管理器：它会机械地 ``nack(requeue=True)``
        无法表达三态，且与手动 ACK 重复触发 ``ignore_processed`` 抑制。

        Args:
            callback: 消费回调，入参为字符串 Payload，返回 :class:`ConsumerResult`。
        """
        await self.connect()
        if self._outbound_queue is None or self._dlx is None:
            await self.ensure_topology()
        assert self._outbound_queue is not None
        assert self._dlx is not None

        logger.info("[RABBITMQ-CLIENT] 启动出站消息 AMQP 监听消费者...")

        async with self._outbound_queue.iterator() as queue_iter:
            async for message in queue_iter:
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

                    result = await callback(payload)
                    await self._route_message(message, result, reason=None)
                except Exception as exc:
                    logger.exception("[RABBITMQ-CLIENT] 处理出站消息异常: {}", exc)
                    # 异常视为不可重试失败，避免 nack(requeue=True) 触发无限重试
                    try:
                        await self._route_message(
                            message,
                            ConsumerResult.DLQ,
                            reason=f"consumer_exception:{type(exc).__name__}",
                        )
                    except Exception:
                        # DLQ 也失败的最后兜底：丢弃消息，避免阻塞队列
                        logger.exception(
                            "[RABBITMQ-CLIENT] DLQ 转投也失败，消息将被丢弃: {}",
                            message.body[:200],
                        )
                        await message.nack(requeue=False)
                finally:
                    if trace_token is not None:
                        reset_trace_context(trace_token)

    async def _route_message(
        self,
        message: aio_pika.IncomingMessage,
        result: ConsumerResult,
        *,
        reason: str | None,
    ) -> None:
        """根据 :class:`ConsumerResult` 路由消息到 ACK / RETRY / DLQ。

        Args:
            message: 待处理的 AMQP 消息。
            result: 回调返回的处理结果。
            reason: 死信原因（仅 DLQ 路径使用），用于附加到死信消息 header 便于排查。
        """
        if result is ConsumerResult.ACK:
            await message.ack()
            return

        if result is ConsumerResult.DLQ:
            await self._publish_to_dlq(message, reason=reason or "callback_marked_dlq")
            await message.ack()
            return

        # ConsumerResult.RETRY
        retry_count = _read_retry_count(message.headers)
        if retry_count >= MAX_RETRY_COUNT:
            logger.warning(
                "[RABBITMQ-CLIENT] 消息重试次数达上限 {}，转 DLQ (retry_count={})",
                MAX_RETRY_COUNT,
                retry_count,
            )
            await self._publish_to_dlq(
                message,
                reason=reason or f"retry_exhausted:{retry_count}",
            )
            await message.ack()
            return

        await self._republish_for_retry(message, retry_count + 1)
        await message.ack()

    async def _publish_to_dlq(
        self,
        message: aio_pika.IncomingMessage,
        *,
        reason: str,
    ) -> None:
        """将原消息转发至 DLQ，附加死信原因与原 retry_count。

        保留原 body、trace headers，附加 ``x-dead-letter-reason`` 与原
        ``x-retry-count``，便于 DLQ 消费端排查。
        """
        assert self._dlx is not None
        headers = dict(message.headers or {})
        headers[DEAD_LETTER_REASON_HEADER] = reason
        # 保留原 retry_count 便于排查，不再递增
        retry_count = _read_retry_count(message.headers)
        headers[RETRY_COUNT_HEADER] = retry_count

        dlq_message = aio_pika.Message(
            body=message.body,
            headers=headers,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type=message.content_type or "application/json",
            correlation_id=message.correlation_id,
            message_id=message.message_id,
        )
        await self._dlx.publish(dlq_message, routing_key=DLQ_ROUTING_KEY)
        logger.warning(
            "[RABBITMQ-CLIENT] 消息已转 DLQ (reason={}, retry_count={}, body_len={})",
            reason,
            retry_count,
            len(message.body),
        )

    async def _republish_for_retry(
        self,
        message: aio_pika.IncomingMessage,
        retry_count: int,
    ) -> None:
        """递增 ``x-retry-count`` 后重新 publish 到原 exchange，触发重试。

        采用「重发 + ACK 原消息」而非 ``nack(requeue=True)``：后者无法修改 header，
        无法跟踪重试次数。
        """
        assert self._exchange is not None
        headers = dict(message.headers or {})
        headers[RETRY_COUNT_HEADER] = retry_count

        retry_message = aio_pika.Message(
            body=message.body,
            headers=headers,
            delivery_mode=aio_pika.DeliveryMode.PERSISTENT,
            content_type=message.content_type or "application/json",
            correlation_id=message.correlation_id,
            message_id=message.message_id,
        )
        await self._exchange.publish(retry_message, routing_key=OUTBOUND_ROUTING_KEY)
        logger.info(
            "[RABBITMQ-CLIENT] 消息重试投递 (retry_count={}/{})",
            retry_count,
            MAX_RETRY_COUNT,
        )

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
