# -*- coding: utf-8 -*-
"""飞书消息协议适配器。

负责在飞书的原生 Event/API Payload 与全局归一化 StandardMessage 协议之间进行双向翻译，
并接管多模态媒体资源（图片）在 MinIO 上的存储寿命周期。
"""

import io
import json
import uuid
from typing import Any
from urllib.parse import urlparse

import lark_oapi as lark
from loguru import logger

from src.core.hub import hub
from src.core.schemas import MessageContent, StandardMessage
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
        # 投递入站消息给路由中枢
        hub.process_inbound(standard_msg)

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

        # 构造统一的富文本骨架
        post_content: dict[str, Any] = {
            "zh_cn": {
                "title": "",
                "content": []
            }
        }

        # 遍历所有内容区块，统一翻译并合并进富文本段落中
        for item in msg.content:
            if item.msg_type == "text":
                text_content = item.text or ""
                post_content["zh_cn"]["content"].append(
                    [{"tag": "text", "text": text_content}]
                )

            elif item.msg_type == "image":
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

            elif item.msg_type == "audio":
                file_url = item.file_url or ""
                post_content["zh_cn"]["content"].append([
                    {"tag": "text", "text": "🎵 语音消息: "},
                    {"tag": "a", "href": file_url, "text": "点击播放音频"}
                ])

            elif item.msg_type == "video":
                file_url = item.file_url or ""
                post_content["zh_cn"]["content"].append([
                    {"tag": "text", "text": "🎥 视频消息: "},
                    {"tag": "a", "href": file_url, "text": "点击观看视频"}
                ])

            elif item.msg_type == "file":
                file_url = item.file_url or ""
                file_name = item.file_name or "点击下载文件"
                post_content["zh_cn"]["content"].append([
                    {"tag": "text", "text": f"📎 附件 ({file_name}): "},
                    {"tag": "a", "href": file_url, "text": "点击下载"}
                ])



        # 根据内容区块数量判定是否需要包装外层 "post" 键
        if len(msg.content) > 1:
            post_data = {"post": post_content}
            raw_post_content = lark.JSON.marshal(post_data)
        else:
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
