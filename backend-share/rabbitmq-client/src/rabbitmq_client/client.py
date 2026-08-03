"""原生 RabbitMQ 异步 AMQP 客户端 (基于 aio-pika)。

提供连接管理、拓扑自动创建、网关消息发布与下行消息监听消费功能。
支持普通队列与 VIP 队列分流。
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
# 注意：拓扑名称（EXCHANGE_NAME 等）不在此处定义，而是在 RabbitMQClient.__init__
# 中通过 os.getenv 延迟读取。原因是 Nacos 配置在模块导入之后才注入 os.environ
# （见 main.py _load_service_configuration），若在此处固化会导致 Nacos 配置
# 不生效，share 包与 backend-data 引用不同拓扑、消息丢失。

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
        # 拓扑名称延迟读取：在 __init__ 中通过 os.getenv 读取，此时 Nacos 配置
        # 已通过 _load_service_configuration() 注入 os.environ，确保 Nacos 配置生效。
        # 若 Nacos 未配置，使用默认值（与 backend-data Settings 默认值一致）。
        self.exchange_name = os.getenv("RABBITMQ_EXCHANGE", "digital_employee.events")
        # ── 普通队列 ──
        self.normal_inbound_queue_name = os.getenv("RABBITMQ_NORMAL_INBOUND_QUEUE", "normal_inbound_queue")
        self.normal_outbound_queue_name = os.getenv("RABBITMQ_NORMAL_OUTBOUND_QUEUE", "normal_outbound_queue")
        self.normal_inbound_routing_key = os.getenv("RABBITMQ_NORMAL_INBOUND_ROUTING_KEY", "normal.inbound.message")
        self.normal_outbound_routing_key = os.getenv("RABBITMQ_NORMAL_OUTBOUND_ROUTING_KEY", "normal.outbound.message")
        # ── VIP 队列 ──
        self.vip_inbound_queue_name = os.getenv("RABBITMQ_VIP_INBOUND_QUEUE", "vip_inbound_queue")
        self.vip_outbound_queue_name = os.getenv("RABBITMQ_VIP_OUTBOUND_QUEUE", "vip_outbound_queue")
        self.vip_inbound_routing_key = os.getenv("RABBITMQ_VIP_INBOUND_ROUTING_KEY", "vip.inbound.message")
        self.vip_outbound_routing_key = os.getenv("RABBITMQ_VIP_OUTBOUND_ROUTING_KEY", "vip.outbound.message")
        # ── 普通死信 ──
        self.dlx_name = os.getenv("RABBITMQ_DLX", "digital_employee.dlx")
        self.dlq_name = os.getenv("RABBITMQ_DLQ", "outbound_dlq")
        self.dlq_routing_key = self.normal_outbound_routing_key
        # ── VIP 死信 ──
        self.vip_dlx_name = os.getenv("RABBITMQ_VIP_DLX", "digital_employee.vip.dlx")
        self.vip_dlq_name = os.getenv("RABBITMQ_VIP_DLQ", "vip_outbound_dlq")
        self.vip_dlq_routing_key = self.vip_outbound_routing_key

        self._connection: aio_pika.RobustConnection | None = None
        self._channel: aio_pika.RobustChannel | None = None
        self._exchange: aio_pika.RobustExchange | None = None
        # 普通队列引用
        self._normal_inbound_queue: aio_pika.RobustQueue | None = None
        self._normal_outbound_queue: aio_pika.RobustQueue | None = None
        # VIP 队列引用
        self._vip_inbound_queue: aio_pika.RobustQueue | None = None
        self._vip_outbound_queue: aio_pika.RobustQueue | None = None
        # 死信交换机引用
        self._dlx: aio_pika.RobustExchange | None = None
        self._dlq_queue: aio_pika.RobustQueue | None = None
        self._vip_dlx: aio_pika.RobustExchange | None = None
        self._vip_dlq_queue: aio_pika.RobustQueue | None = None
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
        """建立并确认 RabbitMQ Exchange 与 Queue 拓扑（含普通+VIP 队列及死信）。"""
        await self.connect()
        assert self._channel is not None

        # 声明 Topic 交换机
        self._exchange = await self._channel.declare_exchange(
            self.exchange_name,
            type=aio_pika.ExchangeType.TOPIC,
            durable=True,
        )

        # ── 普通入站队列 ──
        self._normal_inbound_queue = await self._channel.declare_queue(
            self.normal_inbound_queue_name,
            durable=True,
        )
        await self._normal_inbound_queue.bind(self._exchange, routing_key=self.normal_inbound_routing_key)

        # ── 普通出站队列 ──
        self._normal_outbound_queue = await self._channel.declare_queue(
            self.normal_outbound_queue_name,
            durable=True,
        )
        await self._normal_outbound_queue.bind(self._exchange, routing_key=self.normal_outbound_routing_key)

        # ── VIP 入站队列 ──
        self._vip_inbound_queue = await self._channel.declare_queue(
            self.vip_inbound_queue_name,
            durable=True,
        )
        await self._vip_inbound_queue.bind(self._exchange, routing_key=self.vip_inbound_routing_key)

        # ── VIP 出站队列 ──
        self._vip_outbound_queue = await self._channel.declare_queue(
            self.vip_outbound_queue_name,
            durable=True,
        )
        await self._vip_outbound_queue.bind(self._exchange, routing_key=self.vip_outbound_routing_key)

        # ── 普通死信拓扑：DLX (direct) + DLQ ──
        self._dlx = await self._channel.declare_exchange(
            self.dlx_name,
            type=aio_pika.ExchangeType.DIRECT,
            durable=True,
        )
        self._dlq_queue = await self._channel.declare_queue(
            self.dlq_name,
            durable=True,
        )
        await self._dlq_queue.bind(self._dlx, routing_key=self.dlq_routing_key)

        # ── VIP 死信拓扑：独立 DLX (direct) + DLQ ──
        self._vip_dlx = await self._channel.declare_exchange(
            self.vip_dlx_name,
            type=aio_pika.ExchangeType.DIRECT,
            durable=True,
        )
        self._vip_dlq_queue = await self._channel.declare_queue(
            self.vip_dlq_name,
            durable=True,
        )
        await self._vip_dlq_queue.bind(self._vip_dlx, routing_key=self.vip_dlq_routing_key)

        self.is_available = True
        logger.info(
            "[RABBITMQ-CLIENT] 消息拓扑建立成功 (exchange={}, normal_dlx={}, vip_dlx={})",
            self.exchange_name,
            self.dlx_name,
            self.vip_dlx_name,
        )
        return {
            "connected": True,
            "exchange": self.exchange_name,
            "normal_inbound_queue": self.normal_inbound_queue_name,
            "normal_outbound_queue": self.normal_outbound_queue_name,
            "vip_inbound_queue": self.vip_inbound_queue_name,
            "vip_outbound_queue": self.vip_outbound_queue_name,
            "dlx": self.dlx_name,
            "dlq": self.dlq_name,
            "vip_dlx": self.vip_dlx_name,
            "vip_dlq": self.vip_dlq_name,
        }

    async def publish_inbound(
        self,
        *,
        platform: str,
        bot_id: str,
        payload: str,
        vip: bool = False,
    ) -> dict[str, Any]:
        """将网关上行消息发布至 RabbitMQ 入站队列。

        Args:
            platform: IM 平台类型。
            bot_id: Bot 实例 ID。
            payload: 消息 JSON 字符串。
            vip: 是否为 VIP 消息。True 时发布到 VIP 入站队列，否则发布到普通入站队列。
        """
        await self.connect()
        if self._exchange is None:
            await self.ensure_topology()
        assert self._exchange is not None

        routing_key = self.vip_inbound_routing_key if vip else self.normal_inbound_routing_key

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

        await self._exchange.publish(amqp_message, routing_key=routing_key)
        self.is_available = True
        return {"status": "published", "routing_key": routing_key, "vip": vip}

    async def start_outbound_consumer(
        self,
        callback: Callable[[str], Awaitable[ConsumerResult]],
        *,
        vip: bool = False,
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
            vip: 是否消费 VIP 出站队列。True 消费 vip_outbound_queue，False 消费 normal_outbound_queue。
        """
        await self.connect()
        queue_name = "vip" if vip else "normal"
        if vip:
            target_queue = self._vip_outbound_queue
            target_dlx = self._vip_dlx
        else:
            target_queue = self._normal_outbound_queue
            target_dlx = self._dlx

        if target_queue is None or target_dlx is None:
            await self.ensure_topology()
            if vip:
                target_queue = self._vip_outbound_queue
                target_dlx = self._vip_dlx
            else:
                target_queue = self._normal_outbound_queue
                target_dlx = self._dlx

        assert target_queue is not None
        assert target_dlx is not None

        logger.info("[RABBITMQ-CLIENT] 启动 {} 出站消息 AMQP 监听消费者...", queue_name)

        async with target_queue.iterator() as queue_iter:
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
                    await self._route_message(message, result, reason=None, vip=vip)
                except Exception as exc:
                    logger.exception("[RABBITMQ-CLIENT] 处理 {} 出站消息异常: {}", queue_name, exc)
                    # 异常视为不可重试失败，避免 nack(requeue=True) 触发无限重试
                    try:
                        await self._route_message(
                            message,
                            ConsumerResult.DLQ,
                            reason=f"consumer_exception:{type(exc).__name__}",
                            vip=vip,
                        )
                    except Exception:
                        # DLQ 也失败的最后兜底：丢弃消息，避免阻塞队列
                        logger.exception(
                            "[RABBITMQ-CLIENT] {} DLQ 转投也失败，消息将被丢弃: {}",
                            queue_name,
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
        vip: bool = False,
    ) -> None:
        """根据 :class:`ConsumerResult` 路由消息到 ACK / RETRY / DLQ。

        Args:
            message: 待处理的 AMQP 消息。
            result: 回调返回的处理结果。
            reason: 死信原因（仅 DLQ 路径使用），用于附加到死信消息 header 便于排查。
            vip: 是否为 VIP 消息，影响 DLQ 和重试的目标。
        """
        if result is ConsumerResult.ACK:
            await message.ack()
            return

        if result is ConsumerResult.DLQ:
            await self._publish_to_dlq(message, reason=reason or "callback_marked_dlq", vip=vip)
            await message.ack()
            return

        # ConsumerResult.RETRY
        retry_count = _read_retry_count(message.headers)
        if retry_count >= MAX_RETRY_COUNT:
            logger.warning(
                "[RABBITMQ-CLIENT] 消息重试次数达上限 {}，转 {} DLQ (retry_count={})",
                MAX_RETRY_COUNT,
                "vip" if vip else "normal",
                retry_count,
            )
            await self._publish_to_dlq(
                message,
                reason=reason or f"retry_exhausted:{retry_count}",
                vip=vip,
            )
            await message.ack()
            return

        await self._republish_for_retry(message, retry_count + 1, vip=vip)
        await message.ack()

    async def _publish_to_dlq(
        self,
        message: aio_pika.IncomingMessage,
        *,
        reason: str,
        vip: bool = False,
    ) -> None:
        """将原消息转发至 DLQ，附加死信原因与原 retry_count。

        保留原 body、trace headers，附加 ``x-dead-letter-reason`` 与原
        ``x-retry-count``，便于 DLQ 消费端排查。

        Args:
            message: 待转 DLQ 的消息。
            reason: 死信原因。
            vip: 是否为 VIP 消息。True 时转发到 VIP DLQ，否则转发到普通 DLQ。
        """
        if vip:
            assert self._vip_dlx is not None
            dlx = self._vip_dlx
            dlq_rk = self.vip_dlq_routing_key
        else:
            assert self._dlx is not None
            dlx = self._dlx
            dlq_rk = self.dlq_routing_key

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
        await dlx.publish(dlq_message, routing_key=dlq_rk)
        level = "VIP" if vip else "NORMAL"
        logger.warning(
            "[RABBITMQ-CLIENT] {} 消息已转 DLQ (reason={}, retry_count={}, body_len={})",
            level,
            reason,
            retry_count,
            len(message.body),
        )

    async def _republish_for_retry(
        self,
        message: aio_pika.IncomingMessage,
        retry_count: int,
        *,
        vip: bool = False,
    ) -> None:
        """递增 ``x-retry-count`` 后重新 publish 到原 exchange，触发重试。

        采用「重发 + ACK 原消息」而非 ``nack(requeue=True)``：后者无法修改 header，
        无法跟踪重试次数。

        Args:
            message: 待重试的消息。
            retry_count: 新的重试次数。
            vip: 是否为 VIP 消息。True 时使用 VIP 出站路由键，否则使用普通出站路由键。
        """
        assert self._exchange is not None
        routing_key = self.vip_outbound_routing_key if vip else self.normal_outbound_routing_key
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
        await self._exchange.publish(retry_message, routing_key=routing_key)
        level = "VIP" if vip else "NORMAL"
        logger.info(
            "[RABBITMQ-CLIENT] {} 消息重试投递 (retry_count={}/{})",
            level,
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