# -*- coding: utf-8 -*-
"""内存消息中枢。

负责全局消息路由（Inbound/Outbound 切面）以及线程隔离调度，规避大模型推理和文件上传对长连接的阻塞。
"""

import concurrent.futures
import time
from typing import Any, Callable

from loguru import logger

from src.core.schemas import StandardMessage


class MessageHub:
    """消息路由与调度中枢单例类。"""

    def __init__(self) -> None:
        # 建立专用的后台工作线程池，最大并发工作线程数为 20
        self.executor: concurrent.futures.ThreadPoolExecutor = (
            concurrent.futures.ThreadPoolExecutor(
                max_workers=20,
                thread_name_prefix="AgentWorker",
            )
        )
        # 提供动态注入的 Bot 实例提供者，规避与 manager.py 循环导包
        self.get_bot_func: Callable[[str], Any] | None = None

    def register_bot_provider(self, provider_func: Callable[[str], Any]) -> None:
        """注册 Bot 实例获取函数委托（解耦）。

        Args:
            provider_func: 接收 bot_id 并返回 Bot 实例的函数。
        """
        self.get_bot_func = provider_func
        logger.info("MessageHub 已成功注入外部 Bot 查找委托。")

    def process_inbound(self, msg: StandardMessage) -> None:
        """【入站切面】投递任务并瞬间返回，绝不阻塞底层长连接线程。

        将归一化消息提交至后台线程池进行 AI 业务大脑交互。

        Args:
            msg: 归一化标准消息对象。
        """
        logger.info(
            "[HUB-IN] 收到 {} 会话 {} 消息，消息体区块数量={}, 异步分发至线程池中...",
            msg.platform,
            msg.session_id,
            len(msg.content),
        )
        self.executor.submit(self._mock_agent_process, msg)

    def process_outbound(self, msg: StandardMessage) -> None:
        """【出站切面】路由并分发回具体的 Bot 平台适配器。

        Args:
            msg: 回复的归一化标准消息对象。
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
            "[HUB-OUT] 分发回复指令至 {} 适配器 (BotID: {})",
            msg.platform,
            msg.bot_id,
        )
        # 将消息递交给适配器出站层发送
        bot_instance.adapter.send_message(msg)

    def _mock_agent_process(self, msg: StandardMessage) -> None:
        """【模拟 Agent 大脑】在工作线程内处理高耗时 AI 业务并返回回复。

        如果是文本消息，模拟 1.0 秒延迟并加上处理前缀后返回。
        如果是多模态消息（图片、富文本），直接原样流转回出站切面。

        Args:
            msg: 收到的标准输入消息。
        """
        try:
            logger.debug(
                "[AgentWorker] 线程正在处理消息 (SessionID: {})...",
                msg.session_id,
            )
            time.sleep(1.0)  # 模拟 AI 模型回复计算耗时

            # 深拷贝一份并修改内容，原样发回 (Echo 模式)
            reply_msg = msg.model_copy(deep=True)
            for item in reply_msg.content:
                if item.msg_type == "text" and item.text:
                    item.text = f"【中枢处理完成】已收到指令: {item.text}"

            logger.debug(
                "[AgentWorker] 处理完成，投递至出站切面 (SessionID: {}).",
                msg.session_id,
            )
            self.process_outbound(reply_msg)
        except Exception as exc:
            logger.error("[AgentWorker] 业务处理线程抛出异常: {}", exc)


# 全局唯一的消息路由中枢单例
hub: MessageHub = MessageHub()
