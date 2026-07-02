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

        # 3. 富文本消息类型转换
        elif msg_type == "post":
            try:
                post_content = json.loads(event.message.content)
            except Exception as exc:
                logger.warning(
                    "[BotID: {}] 解析富文本内容 JSON 异常: {}",
                    self.bot.bot_id,
                    exc,
                )
                return

            # 遍历并递归替换富文本里所有 img 标签的 image_key
            self._recursive_transfer_post_images(
                post_detail=post_content,
                message_id=message_id,
                session_id=session_id,
            )

            # 将已转存完、包含 MinIO 链接的富文本结构作为 JSON 序列化存入 text
            raw_post_str = json.dumps(post_content, ensure_ascii=False)
            standard_msg.content.append(
                MessageContent(msg_type="post", text=raw_post_str)
            )

        else:
            logger.debug(
                "[BotID: {}] 忽略非处理入站消息类型: {}",
                self.bot.bot_id,
                msg_type,
            )
            return

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

            elif item.msg_type == "post":
                try:
                    parsed_post = json.loads(item.text or "{}")
                except Exception as exc:
                    logger.error(
                        "[BotID: {}] 解析出站富文本内容 JSON 失败: {}",
                        self.bot.bot_id,
                        exc,
                    )
                    continue

                # 递归恢复富文本中的图片链接
                self._recursive_restore_post_images(parsed_post)

                # 将其内部的段落合并至主富文本的对应语言中
                for lang, post_detail in parsed_post.items():
                    if not isinstance(post_detail, dict):
                        continue
                    if lang not in post_content:
                        post_content[lang] = {
                            "title": post_detail.get("title", ""),
                            "content": []
                        }
                    paragraphs = post_detail.get("content", [])
                    if isinstance(paragraphs, list):
                        post_content[lang]["content"].extend(paragraphs)

        # 最外层包装 "post" 键
        post_data = {"post": post_content}
        raw_post_content = lark.JSON.marshal(post_data)

        if msg.chat_type == "p2p":
            self._send_post_p2p(msg.session_id, raw_post_content)
        elif msg.chat_type == "group":
            self._reply_post_group(msg.message_id, raw_post_content)

    # ==========================================
    # 多模态资源置换核心逻辑（MinIO <--> 飞书）
    # ==========================================

    def _transfer_feishu_to_minio(
        self, *, message_id: str, file_key: str, session_id: str
    ) -> str | None:
        """从飞书下载图片二进制，存入 MinIO 并获取内部标准 URL。"""
        try:
            # 1. 调用飞书接口下载图片
            req = (
                lark.im.v1.GetMessageResourceRequest.builder()
                .message_id(message_id)
                .file_key(file_key)
                .type("image")
                .build()
            )
            resp = self.bot.api_client.im.v1.message_resource.get(req)
            if not resp.success():
                logger.error(
                    "[BotID: {}] 下载飞书资源流失败: code={}, msg={}",
                    self.bot.bot_id,
                    resp.code,
                    resp.msg,
                )
                return None

            img_bytes = resp.file.getvalue()
            length = len(img_bytes)

            # 2. 构造唯一文件名，上传到 MinIO
            file_extension = ".png"  # 飞书资源通常默认为图片
            object_name = f"feishu/{self.bot.bot_id}/{session_id}/{uuid.uuid4()}{file_extension}"

            minio_url = minio_client.upload_file(
                object_name=object_name,
                data=io.BytesIO(img_bytes),
                length=length,
                content_type="image/png",
            )
            return minio_url
        except Exception as exc:
            logger.error(
                "[BotID: {}] 飞书文件转存 MinIO 过程发生异常: {}",
                self.bot.bot_id,
                exc,
            )
            return None

    def _transfer_minio_to_feishu(self, file_url: str) -> str | None:
        """从 MinIO 下载图片二进制，上传到飞书以置换获取 image_key。"""
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

            # 2. 上传到飞书
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
        except Exception as exc:
            logger.error(
                "[BotID: {}] MinIO 转传飞书过程发生异常: {}",
                self.bot.bot_id,
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

    def _recursive_transfer_post_images(
        self, *, post_detail: Any, message_id: str, session_id: str
    ) -> None:
        """递归解析富文本结构，将里面所有的 img 标签 image_key 下载并转存至 MinIO。"""
        if isinstance(post_detail, dict):
            if post_detail.get("tag") == "img":
                old_key = post_detail.get("image_key")
                if old_key and not old_key.startswith("http"):
                    # 发现飞书原生 image_key，转存
                    minio_url = self._transfer_feishu_to_minio(
                        message_id=message_id,
                        file_key=old_key,
                        session_id=session_id,
                    )
                    if minio_url:
                        post_detail["image_key"] = minio_url
            else:
                for val in post_detail.values():
                    self._recursive_transfer_post_images(
                        post_detail=val,
                        message_id=message_id,
                        session_id=session_id,
                    )
        elif isinstance(post_detail, list):
            for item in post_detail:
                self._recursive_transfer_post_images(
                    post_detail=item,
                    message_id=message_id,
                    session_id=session_id,
                )

    def _recursive_restore_post_images(self, post_detail: Any) -> None:
        """递归解析富文本结构，将里面所有的 MinIO URL 下载并置换为飞书原生 image_key。"""
        if isinstance(post_detail, dict):
            if post_detail.get("tag") == "img":
                minio_url = post_detail.get("image_key")
                if minio_url and minio_url.startswith("http"):
                    # 发现 MinIO 的内部标准 URL，置换为飞书 key
                    feishu_key = self._transfer_minio_to_feishu(minio_url)
                    if feishu_key:
                        post_detail["image_key"] = feishu_key
            else:
                for val in post_detail.values():
                    self._recursive_restore_post_images(post_detail=val)
        elif isinstance(post_detail, list):
            for item in post_detail:
                self._recursive_restore_post_images(post_detail=item)

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
