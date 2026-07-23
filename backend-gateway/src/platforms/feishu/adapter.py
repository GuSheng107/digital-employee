# -*- coding: utf-8 -*-
"""飞书消息协议适配器。

负责在飞书的原生 Event/API Payload 与全局归一化 StandardMessage 协议之间进行双向翻译，
并接管多模态媒体资源（图片）在 MinIO 上的存储寿命周期。
"""

import asyncio
import concurrent.futures
import io
import json
import uuid
from typing import Any
from urllib.parse import urlparse

import lark_oapi as lark
from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTrigger,
    P2CardActionTriggerResponse,
)
from loguru import logger

from src.core.hub import hub
from src.core.schemas import MessageContent, MessageType, StandardMessage
from src.platforms.base import BaseAdapter
from src.utils.minio_client import minio_client


class FeishuAdapter(BaseAdapter):
    """飞书平台双向数据翻译与资源置换适配器类。"""

    def __init__(self, bot: Any) -> None:
        """初始化适配器。

        Args:
            bot: 所属的 FeishuBot 实例引用。
        """
        self.bot = bot
        # 异步事件循环引用，由 Bot 在 lifespan 阶段启动后注入
        self.main_loop: asyncio.AbstractEventLoop | None = None
        # 统一从 bot 的配置中读取 Bucket 名称，若无则使用 MinIO 的默认值
        self.bucket_name: str = bot.config.get("minio_bucket_name", minio_client.bucket_name)

    def handle_receive(self, data: lark.im.v1.P2ImMessageReceiveV1) -> None:
        """接收飞书 WebSocket 推送的原始事件，翻译成归一化消息投递至中枢。

        Args:
            data: 飞书推送的消息接收事件实体。
        """
        event = data.event
        chat_type = event.message.chat_type
        sender_id = event.sender.sender_id
        message_id = event.message.message_id
        msg_type = event.message.message_type

        logger.info(
            "[BotID: {}] 收到飞书原始入站推送 JSON -> message_id='{}', msg_type='{}', content='{}'",
            self.bot.bot_id,
            message_id,
            msg_type,
            event.message.content
        )

        # 确定会话 ID（单聊为发送者 open_id，群聊为群聊 ID）
        session_id = (
            sender_id.open_id if chat_type == "p2p" else event.message.chat_id
        )

        # 实例化标准归一化消息体
        standard_msg = StandardMessage(
            message_id=message_id,
            platform="feishu",
            bot_id=self.bot.bot_id,
            chat_type=chat_type,
            session_id=session_id,
            sender_id=sender_id.open_id,
        )

        msg_type = event.message.message_type

        # 1. 文本消息类型转换
        if msg_type == "text":
            user_text = ""
            try:
                content_json = json.loads(event.message.content)
                user_text = content_json.get("text", "")
            except Exception as exc:
                logger.warning(
                    "[BotID: {}] 解析飞书文本内容 JSON 异常: {}",
                    self.bot.bot_id,
                    exc,
                )
                user_text = event.message.content

            standard_msg.content.append(
                MessageContent(msg_type="text", text=user_text)
            )

        # 2. 单张图片消息类型转换
        elif msg_type == "image":
            file_key = ""
            try:
                content_json = json.loads(event.message.content)
                file_key = content_json.get("image_key", "")
            except Exception as exc:
                logger.warning(
                    "[BotID: {}] 解析图片 image_key 异常: {}",
                    self.bot.bot_id,
                    exc,
                )
                return

            if not file_key:
                logger.warning(
                    "[BotID: {}] 消息体内无有效图片 image_key",
                    self.bot.bot_id,
                )
                return

            # 下载飞书私有图片并转存到内部 MinIO
            minio_url = self._transfer_feishu_to_minio(
                message_id=message_id,
                file_key=file_key,
                session_id=session_id,
            )
            if minio_url:
                standard_msg.content.append(
                    MessageContent(msg_type="image", file_url=minio_url)
                )
            else:
                logger.error(
                    "[BotID: {}] 图片转存至 MinIO 失败，终止该消息入站",
                    self.bot.bot_id,
                )
                return

        # 3. 音频消息类型转换
        elif msg_type == "audio":
            file_key = ""
            try:
                content_json = json.loads(event.message.content)
                file_key = content_json.get("file_key", "")
            except Exception as exc:
                logger.warning(
                    "[BotID: {}] 解析音频 file_key 异常: {}",
                    self.bot.bot_id,
                    exc,
                )
                return

            if file_key:
                minio_url = self._transfer_feishu_to_minio(
                    message_id=message_id,
                    file_key=file_key,
                    session_id=session_id,
                    res_type="audio",
                )
                if minio_url:
                    standard_msg.content.append(
                        MessageContent(msg_type="audio", file_url=minio_url)
                    )

        # 4. 视频/媒体消息类型转换
        elif msg_type == "media":
            file_key = ""
            try:
                content_json = json.loads(event.message.content)
                file_key = content_json.get("file_key", "")
            except Exception as exc:
                logger.warning(
                    "[BotID: {}] 解析媒体 file_key 异常: {}",
                    self.bot.bot_id,
                    exc,
                )
                return

            if file_key:
                minio_url = self._transfer_feishu_to_minio(
                    message_id=message_id,
                    file_key=file_key,
                    session_id=session_id,
                    res_type="media",
                )
                if minio_url:
                    standard_msg.content.append(
                        MessageContent(msg_type="video", file_url=minio_url)
                    )

        # 5. 文件消息类型转换
        elif msg_type == "file":
            file_key = ""
            file_name = ""
            try:
                content_json = json.loads(event.message.content)
                file_key = content_json.get("file_key", "")
                file_name = content_json.get("file_name", "file")
            except Exception as exc:
                logger.warning(
                    "[BotID: {}] 解析文件 file_key 异常: {}",
                    self.bot.bot_id,
                    exc,
                )
                return

            if file_key:
                minio_url = self._transfer_feishu_to_minio(
                    message_id=message_id,
                    file_key=file_key,
                    session_id=session_id,
                    res_type="file",
                    file_name=file_name,
                )
                if minio_url:
                    standard_msg.content.append(
                        MessageContent(
                            msg_type="file",
                            file_url=minio_url,
                            file_name=file_name,
                        )
                    )

        # 6. 富文本消息类型转换（降维打散为基础类列表）
        elif msg_type == "post":
            try:
                raw_post_data = json.loads(event.message.content)
            except Exception as exc:
                logger.warning(
                    "[BotID: {}] 解析富文本内容 JSON 异常: {}",
                    self.bot.bot_id,
                    exc,
                )
                return

            # 兼容处理：飞书推送的富文本事件中，content JSON 往往包裹在外层 "post" 键下，需解包以获取语言主节点
            post_content = raw_post_data.get("post", raw_post_data)

            # 自适应兼容：判断最外层是直接平铺 title/content（无语言层），还是带有多语言节点（如 zh_cn）
            if "content" in post_content:
                unified_post_data = {"zh_cn": post_content}
            else:
                unified_post_data = post_content

            # 平铺（Flatten）富文本中的节点到扁平的一维内容列表中，消除 post 类型
            for lang, post_detail in unified_post_data.items():
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
                        tag = element.get("tag")
                        if tag == "text":
                            text_str = element.get("text", "")
                            if text_str:
                                standard_msg.content.append(
                                    MessageContent(msg_type="text", text=text_str)
                                )
                        elif tag == "img":
                            old_key = element.get("image_key")
                            if old_key:
                                minio_url = self._transfer_feishu_to_minio(
                                    message_id=message_id,
                                    file_key=old_key,
                                    session_id=session_id,
                                )
                                if minio_url:
                                    standard_msg.content.append(
                                        MessageContent(msg_type="image", file_url=minio_url)
                                    )
                        elif tag == "a":
                            text_str = element.get("text", "")
                            href = element.get("href", "")
                            if text_str:
                                standard_msg.content.append(
                                    MessageContent(msg_type="text", text=f"[{text_str}]({href})")
                                )

        else:
            logger.debug(
                "[BotID: {}] 忽略非处理入站消息类型: {}",
                self.bot.bot_id,
                msg_type,
            )
            return

        logger.info(
            "[BotID: {}] 投递入站消息，归一化 StandardMessage JSON: {}",
            self.bot.bot_id,
            standard_msg.model_dump_json(indent=2)
        )
        # 通过跨线程安全搭桥投递入站消息给异步路由中枢
        self._submit_to_hub(standard_msg)

    def _submit_to_hub(self, msg: StandardMessage) -> None:
        """将归一化消息安全地从同步长连接线程投递至异步事件循环中枢。

        使用 asyncio.run_coroutine_threadsafe 跨越线程边界，并通过
        Future.result(timeout) 显式捕获投递异常，杜绝消息静默丢失。

        Args:
            msg: 归一化标准消息对象。
        """
        if self.main_loop is None or self.main_loop.is_closed():
            logger.error(
                "[BotID: {}] 主事件循环未注入或已关闭，无法投递消息至中枢。",
                self.bot.bot_id,
            )
            return

        future = asyncio.run_coroutine_threadsafe(
            hub.process_inbound(msg),
            self.main_loop,
        )

        try:
            # 阻塞等待异步中枢处理结果，若 MQ 投递抛出异常则此处捕获
            future.result(timeout=5.0)
        except concurrent.futures.TimeoutError:
            logger.error(
                "[BotID: {}] 跨线程提交入站任务至异步中枢超时（>5s）。",
                self.bot.bot_id,
            )
        except Exception as exc:
            logger.error(
                "[BotID: {}] 跨线程投递异步中枢时发生异常: {}",
                self.bot.bot_id,
                exc,
            )

    def send_message(self, msg: StandardMessage) -> None:
        """将标准出站消息统一转换打包为飞书富文本（post）格式发送。

        Args:
            msg: 出站的标准归一化消息体。
        """
        if not msg.content:
            logger.warning("[BotID: {}] 待发送的标准消息内容为空，放弃发送。", self.bot.bot_id)
            return

        logger.info(
            "[BotID: {}] 收到待发送出站消息，StandardMessage JSON: {}",
            self.bot.bot_id,
            msg.model_dump_json(indent=2)
        )
        logger.info(
            "[BotID: {}] 开始将标准消息 (区块数量={}) 统一打包为 post 富文本出站...",
            self.bot.bot_id,
            len(msg.content),
        )

        # 检查是否包含卡片消息（MessageType.CARD 或 MessageType.INTERACTIVE）
        for item in msg.content:
            if item.msg_type in (MessageType.CARD, MessageType.INTERACTIVE) and item.card_json:
                card_str = (
                    item.card_json
                    if isinstance(item.card_json, str)
                    else json.dumps(item.card_json, ensure_ascii=False)
                )
                logger.info(
                    "[BotID: {}] 准备发送交互卡片消息 JSON: {}",
                    self.bot.bot_id,
                    card_str,
                )
                if msg.chat_type == "p2p":
                    self._send_card_p2p(msg.session_id, card_str)
                elif msg.chat_type == "group":
                    self._reply_card_group(msg.message_id, card_str)
                return

        # 构造统一的富文本骨架
        post_content: dict[str, Any] = {
            "zh_cn": {
                "title": "",
                "content": []
            }
        }

        # 遍历所有内容区块，统一翻译并合并进富文本段落中
        for item in msg.content:
            if item.msg_type == MessageType.TEXT:
                text_content = item.text or ""
                post_content["zh_cn"]["content"].append(
                    [{"tag": "text", "text": text_content}]
                )

            elif item.msg_type == MessageType.IMAGE:
                file_url = item.file_url or ""
                # 从 MinIO 下载并转传至飞书，置换出飞书专用的 image_key
                feishu_image_key = self._transfer_minio_to_feishu(file_url)
                if feishu_image_key:
                    post_content["zh_cn"]["content"].append(
                        [{"tag": "img", "image_key": feishu_image_key}]
                    )
                else:
                    logger.error(
                        "[BotID: {}] 图片从 MinIO 转传飞书失败，跳过该图片区块。",
                        self.bot.bot_id,
                    )
                    post_content["zh_cn"]["content"].append(
                        [{"tag": "text", "text": "[图片转存失败]"}]
                    )

            elif item.msg_type == MessageType.AUDIO:
                file_url = item.file_url or ""
                post_content["zh_cn"]["content"].append([
                    {"tag": "text", "text": "🎵 语音消息: "},
                    {"tag": "a", "href": file_url, "text": "点击播放音频"}
                ])

            elif item.msg_type == MessageType.VIDEO:
                file_url = item.file_url or ""
                post_content["zh_cn"]["content"].append([
                    {"tag": "text", "text": "🎥 视频消息: "},
                    {"tag": "a", "href": file_url, "text": "点击观看视频"}
                ])

            elif item.msg_type == MessageType.FILE:
                file_url = item.file_url or ""
                file_name = item.file_name or "点击下载文件"
                post_content["zh_cn"]["content"].append([
                    {"tag": "text", "text": f"📎 附件 ({file_name}): "},
                    {"tag": "a", "href": file_url, "text": "点击下载"}
                ])

        # 飞书 V1 发送/回复消息接口中，msg_type="post" 的 content 字符串最外层绝对不能包含 "post" 键
        # 必须直接以多语言节点（如 zh_cn）为根，格式为：{"zh_cn": {"title": "", "content": ...}}
        raw_post_content = lark.JSON.marshal(post_content)

        logger.info(
            "[BotID: {}] 最终分发给飞书 API 的富文本 JSON: {}",
            self.bot.bot_id,
            raw_post_content
        )
        if msg.chat_type == "p2p":
            self._send_post_p2p(msg.session_id, raw_post_content)
        elif msg.chat_type == "group":
            self._reply_post_group(msg.message_id, raw_post_content)

    def handle_card_action(
        self, data: P2CardActionTrigger
    ) -> P2CardActionTriggerResponse:
        """处理飞书交互卡片动作（Card Action）回调事件，归一化为 StandardMessage 文本消息。

        根据飞书卡片回调官方响应规范，返回包装了 Toast 的 P2CardActionTriggerResponse 对象。

        Args:
            data: 飞书推送的卡片交互动作事件实体 (P2CardActionTrigger)。

        Returns:
            符合飞书 SDK 规范的 P2CardActionTriggerResponse 响应实体。
        """
        try:
            event = getattr(data, "event", None) or data
            operator = getattr(event, "operator", None)
            open_id = getattr(operator, "open_id", "") if operator else ""
            context = getattr(event, "context", None)
            open_message_id = getattr(context, "open_message_id", "") if context else ""
            open_chat_id = getattr(context, "open_chat_id", "") if context else ""

            chat_type = "group" if open_chat_id else "p2p"
            session_id = open_chat_id if chat_type == "group" else open_id

            action = getattr(event, "action", None)
            action_value = getattr(action, "value", {}) if action else {}
            form_value = getattr(action, "form_value", {}) if action else {}
            option_val = getattr(action, "option", "") if action else ""
            input_val = getattr(action, "input_value", "") if action else ""

            logger.info(
                "[BotID: {}] 收到飞书卡片交互事件 -> open_id='{}', action_value='{}', form_value='{}', option='{}'",
                self.bot.bot_id,
                open_id,
                action_value,
                form_value,
                option_val,
            )

            user_choices: list[str] = []
            if isinstance(form_value, dict) and form_value:
                abc_val = form_value.get("option_abc")
                if abc_val:
                    user_choices.append(f"单选结果: {abc_val}")
                custom_d = form_value.get("custom_option_d")
                if custom_d:
                    user_choices.append(f"D选项自填: {custom_d}")

            if not user_choices and option_val:
                user_choices.append(f"单选结果: {option_val}")

            if not user_choices and input_val:
                user_choices.append(f"输入内容: {input_val}")

            if not user_choices and isinstance(action_value, dict) and action_value:
                val_action = action_value.get("action")
                if val_action:
                    user_choices.append(f"卡片动作: {val_action}")

            summary_text = "；".join(user_choices) if user_choices else "提交卡片选项"
            norm_text = f"[卡片提交结果] {summary_text}"

            standard_msg = StandardMessage(
                message_id=open_message_id,
                platform="feishu",
                bot_id=self.bot.bot_id,
                chat_type=chat_type,
                session_id=session_id,
                sender_id=open_id,
                content=[MessageContent(msg_type=MessageType.TEXT, text=norm_text)],
            )

            logger.info(
                "[BotID: {}] 卡片交互成功归一化为文本消息: {}",
                self.bot.bot_id,
                norm_text,
            )
            self._submit_to_hub(standard_msg)

            return P2CardActionTriggerResponse(
                {
                    "toast": {
                        "type": "info",
                        "content": "提交成功！",
                        "i18n": {
                            "zh_cn": "提交成功！",
                            "en_us": "Submitted successfully!",
                        },
                    }
                }
            )
        except Exception as exc:
            logger.error("[BotID: {}] 处理卡片交互事件发生异常: {}", self.bot.bot_id, exc)
            return P2CardActionTriggerResponse(
                {"toast": {"type": "error", "content": "提交处理异常"}}
            )

    # ==========================================
    # 多模态资源置换核心逻辑（MinIO <--> 飞书）
    # ==========================================

    def _transfer_feishu_to_minio(
        self, *, message_id: str, file_key: str, session_id: str, res_type: str = "image", file_name: str | None = None
    ) -> str | None:
        """从飞书下载媒体/文件资源二进制，存入 MinIO 并获取内部标准 URL。"""
        try:
            # 飞书资源下载接口中，图片类型为 "image"，其余（音频、视频、文件）统一为 "file"
            download_type = "image" if res_type == "image" else "file"
            req = (
                lark.im.v1.GetMessageResourceRequest.builder()
                .message_id(message_id)
                .file_key(file_key)
                .type(download_type)
                .build()
            )
            resp = self.bot.api_client.im.v1.message_resource.get(req)
            if not resp.success():
                logger.error(
                    "[BotID: {}] 下载飞书 {} 资源流失败: code={}, msg={}",
                    self.bot.bot_id,
                    res_type,
                    resp.code,
                    resp.msg,
                )
                return None

            file_bytes = resp.file.getvalue()
            length = len(file_bytes)

            # 根据资源类型自适应后缀和 MIME 类型
            if res_type == "image":
                file_extension = ".png"
                content_type = "image/png"
            elif res_type == "audio":
                file_extension = ".mp3"
                content_type = "audio/mp3"
            elif res_type == "media":
                file_extension = ".mp4"
                content_type = "video/mp4"
            else:
                # 文件类型：如果有传入文件名，则尽可能提取出原有后缀
                if file_name and "." in file_name:
                    file_extension = f".{file_name.split('.')[-1]}"
                else:
                    file_extension = ""
                content_type = "application/octet-stream"

            # 构造在桶内唯一的存储对象路径
            unique_name = f"{uuid.uuid4()}{file_extension}"
            object_name = f"feishu/{self.bot.bot_id}/{session_id}/{unique_name}"

            minio_url = minio_client.upload_file(
                object_name=object_name,
                data=io.BytesIO(file_bytes),
                length=length,
                content_type=content_type,
            )
            return minio_url
        except Exception as exc:
            logger.error(
                "[BotID: {}] 飞书文件转存 MinIO 过程发生异常: {}",
                self.bot.bot_id,
                exc,
            )
            return None

    def _transfer_minio_to_feishu(
        self, file_url: str, res_type: str = "image", file_name: str | None = None
    ) -> str | None:
        """从 MinIO 下载媒体/文件资源，并上传至飞书平台，换取发送所需的 key (image_key 或 file_key)。

        Args:
            file_url: 内部 MinIO 资源的完整网络 URL。
            res_type: 资源类型，如 "image", "audio", "video", "file"。
            file_name: 文件名（对于 file 类型是必须的）。

        Returns:
            飞书平台返回的资源唯一 key (image_key 或 file_key)。若失败则返回 None。
        """
        if not file_url:
            return None

        # 从内部标准 URL 解析出 MinIO 的 Object Name
        object_name = self._get_object_name_from_url(file_url)

        try:
            # 1. 从 MinIO 下载
            file_stream = minio_client.download_file(object_name=object_name)
            if file_stream is None:
                logger.error(
                    "[BotID: {}] 从 MinIO 下载资源文件失败: {}",
                    self.bot.bot_id,
                    object_name,
                )
                return None

            # 2. 如果是图片类型，调用飞书图片上传接口
            if res_type == "image":
                upload_req = (
                    lark.im.v1.CreateImageRequest.builder()
                    .request_body(
                        lark.im.v1.CreateImageRequestBody.builder()
                        .image_type("message")
                        .image(file_stream)
                        .build()
                    )
                    .build()
                )
                upload_resp = self.bot.api_client.im.v1.image.create(upload_req)
                if not upload_resp.success():
                    logger.error(
                        "[BotID: {}] 置换飞书图片 key 失败: code={}, msg={}",
                        self.bot.bot_id,
                        upload_resp.code,
                        upload_resp.msg,
                    )
                    return None
                return upload_resp.data.image_key

            # 3. 如果是音频、视频或文件类型，统一调用飞书文件上传接口
            else:
                # 判定飞书文件上传所需的 file_type 细分格式
                if res_type == "audio":
                    file_type = "opus"  # 飞书语音推荐使用 opus
                    actual_name = file_name or "voice.opus"
                elif res_type == "video":
                    file_type = "mp4"
                    actual_name = file_name or "video.mp4"
                else:
                    file_type = "stream"
                    actual_name = file_name or "file.bin"

                upload_req = (
                    lark.im.v1.CreateFileRequest.builder()
                    .request_body(
                        lark.im.v1.CreateFileRequestBody.builder()
                        .file_type(file_type)
                        .file_name(actual_name)
                        .file(file_stream)
                        .build()
                    )
                    .build()
                )
                upload_resp = self.bot.api_client.im.v1.file.create(upload_req)
                if not upload_resp.success():
                    logger.error(
                        "[BotID: {}] 置换飞书文件 key 失败: code={}, msg={}",
                        self.bot.bot_id,
                        upload_resp.code,
                        upload_resp.msg,
                    )
                    return None
                return upload_resp.data.file_key

        except Exception as exc:
            logger.error(
                "[BotID: {}] MinIO 转传飞书过程发生异常 ({}): {}",
                self.bot.bot_id,
                res_type,
                exc,
            )
            return None

    def _get_object_name_from_url(self, file_url: str) -> str:
        """从 MinIO URL 中反向解析对象真实路径。"""
        parsed = urlparse(file_url)
        path = parsed.path.lstrip("/")
        # 去掉桶名称前缀以获取桶内实际路径
        bucket_prefix = self.bucket_name + "/"
        if path.startswith(bucket_prefix):
            return path[len(bucket_prefix) :]

        # 容错降级：直接以 '/' 分割掉第一部分（第一部分是 bucket）
        parts = path.split("/", 1)
        if len(parts) > 1:
            return parts[1]
        return path



    # ==========================================
    # 底层飞书 API 发送方法封装（只使用 V1 统一格式）
    # ==========================================


    def _send_post_p2p(self, open_id: str, post_content: str) -> None:
        """单聊发送富文本消息。"""
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
            resp = self.bot.api_client.im.v1.message.create(req)
            if not resp.success():
                logger.error(
                    "[BotID: {}] 单聊富文本发送失败: code={}, msg={}",
                    self.bot.bot_id,
                    resp.code,
                    resp.msg,
                )
        except Exception as exc:
            logger.error("[BotID: {}] 单聊富文本发送异常: {}", self.bot.bot_id, exc)

    def _reply_post_group(self, message_id: str, post_content: str) -> None:
        """群聊回复富文本消息。"""
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
            resp = self.bot.api_client.im.v1.message.reply(req)
            if not resp.success():
                logger.error(
                    "[BotID: {}] 群聊富文本回复失败: code={}, msg={}",
                    self.bot.bot_id,
                    resp.code,
                    resp.msg,
                )
        except Exception as exc:
            logger.error("[BotID: {}] 群聊富文本回复异常: {}", self.bot.bot_id, exc)

    def _send_card_p2p(self, open_id: str, card_content: str) -> None:
        """单聊发送交互卡片消息。"""
        try:
            req = (
                lark.im.v1.CreateMessageRequest.builder()
                .receive_id_type("open_id")
                .request_body(
                    lark.im.v1.CreateMessageRequestBody.builder()
                    .receive_id(open_id)
                    .msg_type("interactive")
                    .content(card_content)
                    .build()
                )
                .build()
            )
            resp = self.bot.api_client.im.v1.message.create(req)
            if not resp.success():
                logger.error(
                    "[BotID: {}] 单聊交互卡片发送失败: code={}, msg={}",
                    self.bot.bot_id,
                    resp.code,
                    resp.msg,
                )
        except Exception as exc:
            logger.error("[BotID: {}] 单聊交互卡片发送异常: {}", self.bot.bot_id, exc)

    def _reply_card_group(self, message_id: str, card_content: str) -> None:
        """群聊回复交互卡片消息。"""
        try:
            req = (
                lark.im.v1.ReplyMessageRequest.builder()
                .message_id(message_id)
                .request_body(
                    lark.im.v1.ReplyMessageRequestBody.builder()
                    .content(card_content)
                    .msg_type("interactive")
                    .build()
                )
                .build()
            )
            resp = self.bot.api_client.im.v1.message.reply(req)
            if not resp.success():
                logger.error(
                    "[BotID: {}] 群聊交互卡片回复失败: code={}, msg={}",
                    self.bot.bot_id,
                    resp.code,
                    resp.msg,
                )
        except Exception as exc:
            logger.error("[BotID: {}] 群聊交互卡片回复异常: {}", self.bot.bot_id, exc)

