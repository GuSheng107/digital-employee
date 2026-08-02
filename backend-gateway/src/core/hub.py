"""纯异步消息路由中枢。

支持 Test/Prod 双模路由调度：
- Test 模式：通过 asyncio.create_task 挂载至后台协程，由内存 Mock 模拟处理。
- Prod 模式：通过 share/data-client 委托 backend-data 投递消息。
"""

import asyncio
from collections.abc import Callable
from typing import Any

from loguru import logger
from observability import (
    SpanKind,
    TraceEventType,
    TracePayloadType,
    TraceService,
    TraceTrigger,
    trace_operation,
)
from pydantic import ValidationError
from rabbitmq_client import ConsumerResult

from src.core.schemas import (
    MessageContent,
    MessageType,
    QuestionCardData,
    StandardMessage,
)
from src.utils.data_access import message_bus_client
from src.utils.observability import export_trace_batch


class MessageHub:
    """纯异步消息路由与调度中枢单例类。"""

    def __init__(self) -> None:
        # 提供动态注入的 Bot 实例提供者，规避与 manager.py 循环导包
        self.get_bot_func: Callable[[str], Any] | None = None

    def register_bot_provider(self, provider_func: Callable[[str], Any]) -> None:
        """注册 Bot 实例获取函数委托（解耦）。

        Args:
            provider_func: 接收 bot_id 并返回 Bot 实例的函数。
        """
        self.get_bot_func = provider_func

    async def process_inbound(self, msg: StandardMessage) -> None:
        """【纯异步入站切面】根据 Bot 环境模式精简分流。

        Test 模式下通过 asyncio.create_task 挂载至后台协程进行内存模拟；
        Prod 模式下显式 await 调用 backend-data，异常可被上层捕获。

        Args:
            msg: 归一化标准消息对象。
        """
        async with trace_operation(
            service=TraceService.BACKEND_GATEWAY,
            kind=SpanKind.CONSUMER,
            operation="接收 IM 消息",
            trigger=TraceTrigger.PLATFORM_CALLBACK,
            event_type=TraceEventType.BUSINESS_OPERATION,
            payload_type=TracePayloadType.IM_MESSAGE,
            payload=msg.model_dump(mode="json"),
            sink=export_trace_batch,
            attributes={"platform": msg.platform, "bot_id": msg.bot_id},
        ):
            if not self.get_bot_func:
                return

            bot_instance = self.get_bot_func(msg.bot_id)
            if not bot_instance:
                return

            # mode 由 BaseBot.__init__ 从 config 读取，所有平台子类均继承此属性。
            # 不再用 getattr 回落默认值——历史 FeishuBot 漏写 self.mode 导致 prod
            # 模式静默失效的根因即在此回落逻辑。
            mode = bot_instance.mode
            if mode == "test":
                asyncio.create_task(self._mock_agent_process(msg))
            elif mode == "prod":
                payload = msg.model_dump_json()
                try:
                    await message_bus_client.publish(
                        platform=msg.platform,
                        bot_id=msg.bot_id,
                        payload=payload,
                    )
                except Exception:
                    reply_err = msg.model_copy(deep=True)
                    reply_err.content = [
                        MessageContent(
                            msg_type=MessageType.TEXT,
                            text="系统繁忙，服务暂时不可用，请稍后再试。",
                        )
                    ]
                    await self.process_outbound(reply_err)

    async def consume_outbound_payload(self, payload_json: str) -> ConsumerResult:
        """解析 backend-data 领取的消息并转交出站切面。

        Args:
            payload_json: 标准消息 JSON。

        Returns:
            :class:`ConsumerResult`，决定 SDK 侧 ACK/RETRY/DLQ 路由：
            - 消息格式校验失败 → :data:`ConsumerResult.DLQ`（不可重试）
            - 其他异常 → :data:`ConsumerResult.DLQ`（与 SDK 侧异常处理一致）
            - 正常路径透传 :meth:`process_outbound` 的返回值
        """
        async with trace_operation(
            service=TraceService.BACKEND_GATEWAY,
            kind=SpanKind.CONSUMER,
            operation="消费 MQ 出站消息",
            trigger=TraceTrigger.MESSAGE_QUEUE,
            event_type=TraceEventType.MQ_CONSUME,
            payload_type=TracePayloadType.MQ_MESSAGE,
            payload=payload_json,
            sink=export_trace_batch,
        ):
            try:
                std_msg = StandardMessage.model_validate_json(payload_json)
                return await self.process_outbound(std_msg)
            except ValidationError:
                # 消息格式错误，重试无意义，直接进 DLQ
                return ConsumerResult.DLQ
            except Exception:
                logger.exception("[HUB] consume_outbound_payload 解析或投递失败")
                return ConsumerResult.DLQ

    async def process_outbound(self, msg: StandardMessage) -> ConsumerResult:
        """【出站总出口】反归一化发送（承接测试与生产汇流）。

        查找对应 Bot 实例及其适配器，调用适配器的 send_message 方法
        完成消息的反归一化发送。

        Args:
            msg: 出站的标准归一化消息体。

        Returns:
            :class:`ConsumerResult`：
            - 配置缺失（get_bot_func 未注册 / Bot 不存在 / adapter 缺失）→
              :data:`ConsumerResult.DLQ`，重试无意义
            - IM 平台发送失败 → :data:`ConsumerResult.RETRY`，可能瞬时故障
            - 发送成功 → :data:`ConsumerResult.ACK`
        """
        if not self.get_bot_func:
            return ConsumerResult.DLQ

        bot_instance = self.get_bot_func(msg.bot_id)
        if bot_instance is None:
            return ConsumerResult.DLQ

        if not hasattr(bot_instance, "adapter") or bot_instance.adapter is None:
            return ConsumerResult.DLQ
        try:
            async with trace_operation(
                service=TraceService.BACKEND_GATEWAY,
                kind=SpanKind.CLIENT,
                operation="发送 IM 消息",
                trigger=TraceTrigger.PLATFORM_CALLBACK,
                event_type=TraceEventType.EXTERNAL_API,
                payload_type=TracePayloadType.EXTERNAL_REQUEST,
                payload=msg.model_dump(mode="json"),
                sink=export_trace_batch,
                attributes={"platform": msg.platform, "bot_id": msg.bot_id},
            ):
                bot_instance.adapter.send_message(msg)
            return ConsumerResult.ACK
        except Exception:
            # IM 平台发送失败：可能是网络抖动、限流、鉴权过期等，可重试
            logger.exception("[HUB] process_outbound 消息发送失败")
            return ConsumerResult.RETRY

    async def _mock_agent_process(self, msg: StandardMessage) -> None:
        """【保留核心项】纯异步非阻塞本地业务模拟。

        如果是文本消息，模拟 1.0 秒延迟并加上处理前缀后返回。
        如果是多模态消息（图片、富文本），直接原样流转回出站切面。

        Args:
            msg: 收到的标准输入消息。
        """
        try:
            async with trace_operation(
                service=TraceService.BACKEND_GATEWAY,
                kind=SpanKind.INTERNAL,
                operation="测试 AI 处理",
                trigger=TraceTrigger.PLATFORM_CALLBACK,
                event_type=TraceEventType.AI_MODEL,
                payload_type=TracePayloadType.MODEL_INPUT,
                payload=msg.model_dump(mode="json"),
                sink=export_trace_batch,
            ):
                await asyncio.sleep(1.0)

            # 在文本消息归一化（StandardMessage）后，对文本拆分识别 /card 卡片指令
            is_card_cmd = False
            for item in msg.content:
                if item.msg_type == MessageType.TEXT and item.text:
                    text_strip = item.text.strip().lower()
                    if text_strip in (
                        "/card",
                        "!card",
                        "card",
                    ) or text_strip.startswith("/card "):
                        is_card_cmd = True
                        break
                elif item.msg_type == MessageType.CARD:
                    is_card_cmd = True
                    break

            reply_msg = msg.model_copy(deep=True)

            if is_card_cmd:
                common_card = QuestionCardData(
                    title="【测试题目】请选择您的首选方案：",
                    description="**题目：** 在智能员工系统中，您倾向采用哪种底层通信链路？",
                    options=[
                        "方案一 (RabbitMQ 纯异步)",
                        "方案二 (HTTP 直连)",
                        "方案三 (WebSocket 长连接)",
                    ],
                    submit_text="提交选择",
                )
                reply_msg.content = [
                    MessageContent(
                        msg_type=MessageType.CARD,
                        card_data=common_card,
                    )
                ]
            else:
                for item in reply_msg.content:
                    if item.msg_type == MessageType.TEXT and item.text:
                        item.text = f"【TEST 异步模拟大脑】已收到指令: {item.text}"
            async with trace_operation(
                service=TraceService.BACKEND_GATEWAY,
                kind=SpanKind.INTERNAL,
                operation="测试 AI 输出",
                trigger=TraceTrigger.PLATFORM_CALLBACK,
                event_type=TraceEventType.AI_MODEL,
                payload_type=TracePayloadType.MODEL_OUTPUT,
                payload=reply_msg.model_dump(mode="json"),
                sink=export_trace_batch,
            ):
                await self.process_outbound(reply_msg)
        except Exception:
            logger.exception("[HUB] _mock_agent_process 测试处理失败")


# 全局唯一的消息路由中枢单例
hub: MessageHub = MessageHub()
