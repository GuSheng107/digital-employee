# -*- coding: utf-8 -*-
"""飞书 Bot 实现。

基于 lark-oapi 长连接（WebSocket）实现消息的接收与回复。
"""

import asyncio
import json
import io
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

        支持文本消息和图片消息的接收，并原样（Echo 模式）发回给用户。

        Args:
            data: 飞书消息事件结构体。
        """
        event = data.event
        chat_type = event.message.chat_type
        sender_id = event.sender.sender_id
        message_id = event.message.message_id

        # 打印消息原始格式
        logger.info("[{}] 消息原始格式: {}", self.bot_id, event.message.content)

        msg_type = event.message.message_type
        if msg_type == "text":
            self._handle_text_message(event, chat_type, sender_id, message_id)
        elif msg_type == "image":
            self._handle_image_message(event, chat_type, sender_id, message_id)
        elif msg_type == "post":
            self._handle_post_message(event, chat_type, sender_id, message_id)
        else:
            logger.debug(
                "[BotID: {}] 忽略非处理消息类型: {}",
                self.bot_id,
                msg_type,
            )

    def _handle_text_message(
        self, event: Any, chat_type: str, sender_id: Any, message_id: str
    ) -> None:
        """处理接收到的文本消息，实现文本 Echo 回复。"""
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
            "[BotID: {}] 收到 {} 文本消息, 内容: '{}', 准备回复: '{}'",
            self.bot_id,
            chat_type,
            user_text,
            reply_text,
        )

        if chat_type == "p2p":
            self._send_message_to_user(sender_id.open_id, reply_text)
        elif chat_type == "group":
            self._reply_to_group_message(message_id, reply_text)

    def _handle_image_message(
        self, event: Any, chat_type: str, sender_id: Any, message_id: str
    ) -> None:
        """处理接收到的图片消息，实现下载图片、重新上传并原样回复。"""
        # 从消息内容中获取原始图片的 file_key
        file_key = ""
        try:
            content_json = json.loads(event.message.content)
            file_key = content_json.get("image_key", "")
        except Exception as exc:
            logger.warning("[BotID: {}] 解析图片消息内容 JSON 失败: {}", self.bot_id, exc)
            return

        if not file_key:
            logger.warning("[BotID: {}] 消息体中未解析到有效的 image_key 字段", self.bot_id)
            return

        logger.info(
            "[BotID: {}] 收到 {} 图片消息, file_key: '{}', 开始处理下载...",
            self.bot_id,
            chat_type,
            file_key,
        )

        new_image_key = self._download_and_upload_image(message_id, file_key)
        if not new_image_key:
            logger.error("[BotID: {}] 图片下载或上传失败，终止回复", self.bot_id)
            return

        # 发送/回复图片消息
        logger.info(
            "[BotID: {}] 图片重传成功, 获取到新 image_key: '{}', 准备回复...",
            self.bot_id,
            new_image_key,
        )
        if chat_type == "p2p":
            self._send_image_to_user(sender_id.open_id, new_image_key)
        elif chat_type == "group":
            self._reply_image_to_group_message(message_id, new_image_key)

    def _send_message_to_user(self, open_id: str, text: str) -> None:
        """单聊：以应用身份直接向用户发送文本消息。

        Args:
            open_id: 用户唯一标识。
            text: 回复文本内容。
        """
        try:
            content = {"text": text}
            req = (
                lark.im.v1.CreateMessageRequest.builder()
                .receive_id_type("open_id")
                .request_body(
                    lark.im.v1.CreateMessageRequestBody.builder()
                    .receive_id(open_id)
                    .msg_type("text")
                    .content(lark.JSON.marshal(content))
                    .build()
                )
                .build()
            )
            resp = self.api_client.im.v1.message.create(req)
            if not resp.success():
                logger.error(
                    "[BotID: {}] 单聊发送文本失败: code={}, msg={}",
                    self.bot_id,
                    resp.code,
                    resp.msg,
                )
            else:
                logger.info(
                    "[BotID: {}] 单聊发送文本成功: message_id={}",
                    self.bot_id,
                    resp.data.message_id,
                )
        except Exception as exc:
            logger.error("[BotID: {}] 单聊发送文本异常: {}", self.bot_id, exc)

    def _reply_to_group_message(self, message_id: str, text: str) -> None:
        """群聊：对群内某条特定消息进行引用文本回复。

        Args:
            message_id: 被回复的原始消息 ID。
            text: 回复文本内容。
        """
        try:
            content = {"text": text}
            req = (
                lark.im.v1.ReplyMessageRequest.builder()
                .message_id(message_id)
                .request_body(
                    lark.im.v1.ReplyMessageRequestBody.builder()
                    .content(lark.JSON.marshal(content))
                    .msg_type("text")
                    .build()
                )
                .build()
            )
            resp = self.api_client.im.v1.message.reply(req)
            if not resp.success():
                logger.error(
                    "[BotID: {}] 群聊回复文本失败: code={}, msg={}",
                    self.bot_id,
                    resp.code,
                    resp.msg,
                )
            else:
                logger.info(
                    "[BotID: {}] 群聊回复文本成功: message_id={}",
                    self.bot_id,
                    resp.data.message_id,
                )
        except Exception as exc:
            logger.error("[BotID: {}] 群聊回复文本异常: {}", self.bot_id, exc)

    def _send_image_to_user(self, open_id: str, image_key: str) -> None:
        """单聊：向指定用户发送图片消息。

        Args:
            open_id: 用户唯一标识。
            image_key: 飞书图片唯一资源标识。
        """
        try:
            content = {"image_key": image_key}
            req = (
                lark.im.v1.CreateMessageRequest.builder()
                .receive_id_type("open_id")
                .request_body(
                    lark.im.v1.CreateMessageRequestBody.builder()
                    .receive_id(open_id)
                    .msg_type("image")
                    .content(lark.JSON.marshal(content))
                    .build()
                )
                .build()
            )
            resp = self.api_client.im.v1.message.create(req)
            if not resp.success():
                logger.error(
                    "[BotID: {}] 单聊发送图片失败: code={}, msg={}",
                    self.bot_id,
                    resp.code,
                    resp.msg,
                )
            else:
                logger.info(
                    "[BotID: {}] 单聊发送图片成功: message_id={}",
                    self.bot_id,
                    resp.data.message_id,
                )
        except Exception as exc:
            logger.error("[BotID: {}] 单聊发送图片异常: {}", self.bot_id, exc)

    def _reply_image_to_group_message(self, message_id: str, image_key: str) -> None:
        """群聊：引用指定消息进行图片消息回复。

        Args:
            message_id: 被回复的原始消息 ID。
            image_key: 飞书图片唯一资源标识。
        """
        try:
            content = {"image_key": image_key}
            req = (
                lark.im.v1.ReplyMessageRequest.builder()
                .message_id(message_id)
                .request_body(
                    lark.im.v1.ReplyMessageRequestBody.builder()
                    .content(lark.JSON.marshal(content))
                    .msg_type("image")
                    .build()
                )
                .build()
            )
            resp = self.api_client.im.v1.message.reply(req)
            if not resp.success():
                logger.error(
                    "[BotID: {}] 群聊回复图片失败: code={}, msg={}",
                    self.bot_id,
                    resp.code,
                    resp.msg,
                )
            else:
                logger.info(
                    "[BotID: {}] 群聊回复图片成功: message_id={}",
                    self.bot_id,
                    resp.data.message_id,
                )
        except Exception as exc:
            logger.error("[BotID: {}] 群聊回复图片异常: {}", self.bot_id, exc)

    def _handle_post_message(
        self, event: Any, chat_type: str, sender_id: Any, message_id: str
    ) -> None:
        """处理接收到的富文本（post）消息，实现富文本 Echo 原样回复。

        支持富文本中 img 标签图片的自动下载与重新上传。

        Args:
            event: 飞书消息事件体。
            chat_type: 消息场景（p2p 或 group）。
            sender_id: 发送者标识结构。
            message_id: 消息唯一 ID。
        """
        try:
            # 接收事件推送的 content 只有 {"zh_cn": ...} 层级，不包含外层 "post" 键
            content_json = json.loads(event.message.content)
        except Exception as exc:
            logger.warning("[BotID: {}] 解析富文本消息内容 JSON 失败: {}", self.bot_id, exc)
            return

        logger.info(
            "[BotID: {}] 收到 {} 富文本(post)消息, 开始解析并替换包含的图片资源...",
            self.bot_id,
            chat_type,
        )

        # 遍历富文本结构，寻找其中的 img 标签并下载重传
        for lang, post_detail in content_json.items():
            if not isinstance(post_detail, dict):
                continue
            paragraphs = post_detail.get("content", [])
            if not isinstance(paragraphs, list):
                continue
            for paragraph in paragraphs:
                if not isinstance(paragraph, list):
                    continue
                for element in paragraph:
                    if not isinstance(element, dict):
                        continue
                    if element.get("tag") == "img":
                        old_image_key = element.get("image_key")
                        if old_image_key:
                            logger.info(
                                "[BotID: {}] 正在为富文本重传图片 image_key: '{}'",
                                self.bot_id,
                                old_image_key,
                            )
                            new_image_key = self._download_and_upload_image(
                                message_id, old_image_key
                            )
                            if new_image_key:
                                element["image_key"] = new_image_key
                                logger.info(
                                    "[BotID: {}] 富文本图片重传成功, 新 image_key: '{}'",
                                    self.bot_id,
                                    new_image_key,
                                )

        # 按照发送消息格式规范，重新在最外层包装 "post" 键
        post_data = {"post": content_json}
        raw_content = lark.JSON.marshal(post_data)

        if chat_type == "p2p":
            self._send_post_to_user(sender_id.open_id, raw_content)
        elif chat_type == "group":
            self._reply_post_to_group_message(message_id, raw_content)

    def _send_post_to_user(self, open_id: str, post_content: str) -> None:
        """单聊：向指定用户发送富文本（post）消息。

        Args:
            open_id: 用户唯一标识。
            post_content: 富文本格式的消息 JSON 字符串。
        """
        try:
            req = (
                lark.im.v1.CreateMessageRequest.builder()
                .receive_id_type("open_id")
                .request_body(
                    lark.im.v1.CreateMessageRequestBody.builder()
                    .receive_id(open_id)
                    .msg_type("post")
                    .content(post_content)
                    .build()
                )
                .build()
            )
            resp = self.api_client.im.v1.message.create(req)
            if not resp.success():
                logger.error(
                    "[BotID: {}] 单聊发送富文本失败: code={}, msg={}",
                    self.bot_id,
                    resp.code,
                    resp.msg,
                )
            else:
                logger.info(
                    "[BotID: {}] 单聊发送富文本成功: message_id={}",
                    self.bot_id,
                    resp.data.message_id,
                )
        except Exception as exc:
            logger.error("[BotID: {}] 单聊发送富文本异常: {}", self.bot_id, exc)

    def _reply_post_to_group_message(self, message_id: str, post_content: str) -> None:
        """群聊：引用指定消息进行富文本（post）消息回复。

        Args:
            message_id: 被回复的原始消息 ID。
            post_content: 富文本格式的消息 JSON 字符串。
        """
        try:
            req = (
                lark.im.v1.ReplyMessageRequest.builder()
                .message_id(message_id)
                .request_body(
                    lark.im.v1.ReplyMessageRequestBody.builder()
                    .content(post_content)
                    .msg_type("post")
                    .build()
                )
                .build()
            )
            resp = self.api_client.im.v1.message.reply(req)
            if not resp.success():
                logger.error(
                    "[BotID: {}] 群聊回复富文本失败: code={}, msg={}",
                    self.bot_id,
                    resp.code,
                    resp.msg,
                )
            else:
                logger.info(
                    "[BotID: {}] 群聊回复富文本成功: message_id={}",
                    self.bot_id,
                    resp.data.message_id,
                )
        except Exception as exc:
            logger.error("[BotID: {}] 群聊回复富文本异常: {}", self.bot_id, exc)

    def _download_and_upload_image(self, message_id: str, file_key: str) -> str | None:
        """下载消息中的图片二进制数据并重新上传，获取新的 image_key。

        Args:
            message_id: 图片所属的消息 ID。
            file_key: 图片的唯一 file_key / image_key。

        Returns:
            新上传后的 image_key。若下载或上传失败则返回 None。
        """
        # 1. 调用获取消息资源接口下载图片
        try:
            download_req = (
                lark.im.v1.GetMessageResourceRequest.builder()
                .message_id(message_id)
                .file_key(file_key)
                .type("image")
                .build()
            )
            download_resp = self.api_client.im.v1.message_resource.get(download_req)
            if not download_resp.success():
                logger.error(
                    "[BotID: {}] 下载图片资源失败: code={}, msg={}",
                    self.bot_id,
                    download_resp.code,
                    download_resp.msg,
                )
                return None
            img_bytes = download_resp.file.getvalue()
        except Exception as exc:
            logger.error("[BotID: {}] 下载消息图片发生异常: {}", self.bot_id, exc)
            return None

        # 2. 上传处理后的图片二进制内容
        try:
            img_stream = io.BytesIO(img_bytes)
            upload_req = (
                lark.im.v1.CreateImageRequest.builder()
                .request_body(
                    lark.im.v1.CreateImageRequestBody.builder()
                    .image_type("message")
                    .image(img_stream)
                    .build()
                )
                .build()
            )
            upload_resp = self.api_client.im.v1.image.create(upload_req)
            if not upload_resp.success():
                logger.error(
                    "[BotID: {}] 上传图片到飞书平台失败: code={}, msg={}",
                    self.bot_id,
                    upload_resp.code,
                    upload_resp.msg,
                )
                return None
            return upload_resp.data.image_key
        except Exception as exc:
            logger.error("[BotID: {}] 上传图片时发生异常: {}", self.bot_id, exc)
            return None
