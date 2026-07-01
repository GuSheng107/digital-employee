# -*- coding: utf-8 -*-
"""飞书 Bot 实现。

基于 lark-oapi 长连接（WebSocket）实现消息的接收与回复。
"""

import asyncio
import json
import time
from typing import Any

import lark_oapi as lark
from loguru import logger

from src.core.base import BaseBot


class FeishuBot(BaseBot):
    """飞书平台 Bot 实现类。

    维护飞书 WebSocket 长连接，并基于事件机制进行消息接收和自动回复。
    """

    def __init__(self, *, bot_id: str, config: dict[str, Any]) -> None:
        """初始化 FeishuBot。

        Args:
            bot_id: Bot 实例唯一标识。
            config: 包含 app_id 和 app_secret 的配置字典。
        """
        super().__init__(bot_id=bot_id, config=config)
        self.app_id: str = config["app_id"]
        self.app_secret: str = config["app_secret"]

        # 创建 API 客户端用于发消息和回复消息
        self.api_client: lark.Client = (
            lark.Client.builder()
            .app_id(self.app_id)
            .app_secret(self.app_secret)
            .log_level(lark.LogLevel.INFO)
            .build()
        )

        # 注册事件处理器
        self.event_handler: lark.EventDispatcherHandler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._handle_message)
            .build()
        )

        self.ws_client: lark.ws.Client | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def _run(self) -> None:
        """运行 Bot 长连接监听（阻塞主线程）。"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        backoff = 1.0
        while self._is_running:
            try:
                # 强设 lark_oapi 的全局 event loop 实例
                import lark_oapi.ws.client
                lark_oapi.ws.client.loop = self._loop

                logger.info("[BotID: {}] 正在建立飞书长连接...", self.bot_id)
                self.ws_client = lark.ws.Client(
                    self.app_id,
                    self.app_secret,
                    event_handler=self.event_handler,
                    log_level=lark.LogLevel.INFO,
                    auto_reconnect=True,
                )
                self.ws_client.start()
                # 正常退出
                break
            except Exception as exc:
                if not self._is_running:
                    break
                logger.error(
                    "[BotID: {}] 飞书长连接发生异常: {}, {} 秒后重试...",
                    self.bot_id,
                    exc,
                    backoff,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    def _on_stop(self) -> None:
        """停止飞书长连接，并关闭关联事件循环。"""
        if self.ws_client is not None:
            self.ws_client._auto_reconnect = False
            if self._loop is not None and self._loop.is_running():
                # 安全执行网络断开
                future = asyncio.run_coroutine_threadsafe(
                    self.ws_client._disconnect(), self._loop
                )
                try:
                    future.result(timeout=3.0)
                except Exception as exc:
                    logger.debug("[BotID: {}] 断开网络连接时捕获异常: {}", self.bot_id, exc)

        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
            logger.info("[BotID: {}] 已发送停止信号给事件循环", self.bot_id)

    def _handle_message(self, data: lark.im.v1.P2ImMessageReceiveV1) -> None:
        """接收并分发飞书消息事件。

        一期核心业务为 Echo 模式，将接收到的文本消息原样返回。

        Args:
            data: 飞书消息事件结构体。
        """
        event = data.event
        chat_type = event.message.chat_type
        sender_id = event.sender.sender_id
        message_id = event.message.message_id

        # 打印消息原始格式
        logger.info("[{}] 消息原始格式: {}", self.bot_id, event.message.content)

        # 仅处理文本消息，忽略其它非文本事件
        if event.message.message_type != "text":
            logger.debug(
                "[BotID: {}] 忽略非文本消息类型: {}",
                self.bot_id,
                event.message.message_type,
            )
            return

        # 解析用户发来的文本
        user_text = ""
        try:
            content_json = json.loads(event.message.content)
            user_text = content_json.get("text", "")
        except Exception as exc:
            logger.warning("[BotID: {}] 解析消息内容 JSON 失败: {}", self.bot_id, exc)
            user_text = event.message.content

        reply_text = f"[Echo] {user_text}"
        logger.info(
            "[BotID: {}] 收到 {} 消息, 内容: '{}', 准备回复: '{}'",
            self.bot_id,
            chat_type,
            user_text,
            reply_text,
        )

        if chat_type == "p2p":
            self._send_message_to_user(sender_id.open_id, reply_text)
        elif chat_type == "group":
            self._reply_to_group_message(message_id, reply_text)

    def _send_message_to_user(self, open_id: str, text: str) -> None:
        """单聊：以应用身份直接向用户发送消息。

        Args:
            open_id: 用户唯一标识。
            text: 回复文本内容。
        """
        try:
            content = {"text": text}
            req = (
                lark.im.v1.Message.builder()
                .receive_id_type("open_id")
                .receive_id(open_id)
                .msg_type("text")
                .content(lark.JSON.marshal(content))
                .build()
            )
            resp = self.api_client.im.v1.message.create(req)
            if not resp.success():
                logger.error(
                    "[BotID: {}] 单聊发送失败: code={}, msg={}",
                    self.bot_id,
                    resp.code,
                    resp.msg,
                )
            else:
                logger.info(
                    "[BotID: {}] 单聊发送成功: message_id={}",
                    self.bot_id,
                    resp.data.message_id,
                )
        except Exception as exc:
            logger.error("[BotID: {}] 单聊发送异常: {}", self.bot_id, exc)

    def _reply_to_group_message(self, message_id: str, text: str) -> None:
        """群聊：对群内某条特定消息进行引用回复。

        Args:
            message_id: 被回复的原始消息 ID。
            text: 回复文本内容。
        """
        try:
            content = {"text": text}
            req = (
                lark.im.v1.Message.builder()
                .message_id(message_id)
                .msg_type("text")
                .content(lark.JSON.marshal(content))
                .build()
            )
            resp = self.api_client.im.v1.message.reply(req)
            if not resp.success():
                logger.error(
                    "[BotID: {}] 群聊回复失败: code={}, msg={}",
                    self.bot_id,
                    resp.code,
                    resp.msg,
                )
            else:
                logger.info(
                    "[BotID: {}] 群聊回复成功: message_id={}",
                    self.bot_id,
                    resp.data.message_id,
                )
        except Exception as exc:
            logger.error("[BotID: {}] 群聊回复异常: {}", self.bot_id, exc)
