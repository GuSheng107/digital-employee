# -*- coding: utf-8 -*-
"""纯异步消息路由中枢。

支持 Test/Prod 双模路由调度：
- Test 模式：通过 asyncio.create_task 挂载至后台协程，由内存 Mock 模拟处理。
- Prod 模式：通过 await mq_client.publish 异步投递至 RabbitMQ。
"""

import asyncio
import json
from typing import Any, Callable

import aio_pika
from loguru import logger

from src.core.schemas import StandardMessage
from src.utils.rabbitmq import mq_client


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
        logger.info("MessageHub 已成功注入外部 Bot 查找委托。")

    async def process_inbound(self, msg: StandardMessage) -> None:
        """【纯异步入站切面】根据 Bot 环境模式精简分流。

        Test 模式下通过 asyncio.create_task 挂载至后台协程进行内存模拟；
        Prod 模式下显式 await 投递至 RabbitMQ，异常可被上层捕获。

        Args:
            msg: 归一化标准消息对象。
        """
        if not self.get_bot_func:
            logger.error("[HUB-IN] 无法路由消息：未注册 Bot 查找提供者。")
            return

        bot_instance = self.get_bot_func(msg.bot_id)
        if not bot_instance:
            logger.error("[HUB-IN] 找不到对应的机器人配置: {}", msg.bot_id)
            return

        # 默认环境安全降级为 test
        mode = getattr(bot_instance, "mode", "test")

        if mode == "test":
            logger.info(
                "[HUB-IN] 机器人 {} (Test模式)，激活内存异步 Mock 协程",
                msg.bot_id,
            )
            # 通过 asyncio.create_task 挂载至后台，杜绝同步线程池开销与阻塞
            asyncio.create_task(self._mock_agent_process(msg))

        elif mode == "prod":
            logger.info(
                "[HUB-IN] 机器人 {} (Prod模式)，异步投递至 MQ",
                msg.bot_id,
            )
            routing_key = f"msg.inbound.{msg.platform}.{msg.bot_id}"
            payload = msg.model_dump_json()
            try:
                # 显式 await，发生网络异常时可直接被上层 try 结构捕获
                await mq_client.publish(routing_key, payload)
            except Exception as exc:
                logger.error(
                    "[HUB-IN] MQ 消息投递失败 (Bot={}): {}",
                    msg.bot_id,
                    exc,
                )
        else:
            logger.warning(
                "[HUB-IN] 机器人 {} 配置了未知的 mode='{}'",
                msg.bot_id,
                mode,
            )

    async def consume_outbound(
        self, message: aio_pika.IncomingMessage
    ) -> None:
        """【单实例 MQ 消费者回调】监听 q_outbound_to_gateway 固定队列。

        自动管理持久化 ACK/NACK 机制，解析 JSON 为 StandardMessage
        后转交出站切面。

        Args:
            message: RabbitMQ 推送的入站消息对象。
        """
        async with message.process():
            try:
                payload = json.loads(message.body.decode("utf-8"))
                std_msg = StandardMessage(**payload)
                await self.process_outbound(std_msg)
            except Exception as exc:
                logger.error("[HUB-OUT] 消费出站指令异常: {}", exc)

    async def process_outbound(self, msg: StandardMessage) -> None:
        """【出站总出口】反归一化发送（承接测试与生产汇流）。

        查找对应 Bot 实例及其适配器，调用适配器的 send_message 方法
        完成消息的反归一化发送。

        Args:
            msg: 出站的标准归一化消息体。
        """
        if not self.get_bot_func:
            logger.error("[HUB-OUT] 无法路由消息：未注册 Bot 查找提供者。")
            return

        bot_instance = self.get_bot_func(msg.bot_id)
        if bot_instance is None:
            logger.error("[HUB-OUT] 路由失败，找不到指定 Bot 实例: {}", msg.bot_id)
            return

        if not hasattr(bot_instance, "adapter") or bot_instance.adapter is None:
            logger.error(
                "[HUB-OUT] 路由失败，目标 Bot 实例 '{}' 未绑定适配器(Adapter)。",
                msg.bot_id,
            )
            return

        logger.info(
            "[HUB-OUT] 准备向 {} 实例 {} 分发回复",
            msg.platform,
            msg.bot_id,
        )
        try:
            # 飞书适配器的 send_message 目前仍是同步方法（涉及飞书 SDK 同步调用）
            bot_instance.adapter.send_message(msg)
        except Exception as exc:
            logger.error(
                "[HUB-OUT] 适配器发送异常 (Bot={}): {}",
                msg.bot_id,
                exc,
            )

    async def _mock_agent_process(self, msg: StandardMessage) -> None:
        """【保留核心项】纯异步非阻塞本地业务模拟。

        如果是文本消息，模拟 1.0 秒延迟并加上处理前缀后返回。
        如果是多模态消息（图片、富文本），直接原样流转回出站切面。

        Args:
            msg: 收到的标准输入消息。
        """
        try:
            logger.debug(
                "[MockAgent] 协程正在处理消息 (SessionID: {})...",
                msg.session_id,
            )
            # 非阻塞切换，释放协程控制权
            await asyncio.sleep(1.0)

            # 深拷贝一份并修改内容
            reply_msg = msg.model_copy(deep=True)
            for item in reply_msg.content:
                if item.msg_type == "text" and item.text:
                    item.text = f"【TEST 异步模拟大脑】已收到指令: {item.text}"

            logger.debug(
                "[MockAgent] 处理完成，投递至出站切面 (SessionID: {}).",
                msg.session_id,
            )
            await self.process_outbound(reply_msg)
        except Exception as exc:
            logger.error("[MockAgent] 业务处理协程抛出异常: {}", exc)


# 全局唯一的消息路由中枢单例
hub: MessageHub = MessageHub()
