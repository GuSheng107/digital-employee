# -*- coding: utf-8 -*-
"""企业微信消息协议适配器。

负责在企业微信长连接事件 Payload 与全局归一化 StandardMessage 协议之间进行双向翻译，
并接管加密媒体资源解密、MinIO 上的存储生命周期管理以及基于 wecom_aibot_sdk 执行消息的回复。
"""

import asyncio
import base64
import concurrent.futures
import io
import json
import urllib.request
import uuid
from collections import OrderedDict
from typing import Any
from urllib.parse import urlparse

from Crypto.Cipher import AES
from loguru import logger

from src.core.hub import hub
from src.core.schemas import (
    CardOptionItem,
    MessageContent,
    MessageType,
    QuestionCardData,
    StandardMessage,
)
from src.platforms.base import BaseAdapter
from src.utils.minio_client import minio_client


class LRUCache(OrderedDict[str, dict[str, Any]]):
    """使用 OrderedDict 实现的简易 LRU 缓存，用于存储消息 ID 到入站原始帧的映射。"""

    def __init__(self, capacity: int = 1000) -> None:
        """初始化缓存容量。

        Args:
            capacity: 最大容量。
        """
        super().__init__()
        self.capacity = capacity

    def __setitem__(self, key: str, value: dict[str, Any]) -> None:
        """设置缓存值，如果超出容量则弹出最早的项。

        Args:
            key: 消息 ID。
            value: 原始帧数据。
        """
        super().__setitem__(key, value)
        if len(self) > self.capacity:
            self.popitem(last=False)


class WeChatAdapter(BaseAdapter):
    """企业微信平台双向数据翻译与资源解密适配器。"""

    def __init__(self, bot: Any) -> None:
        """初始化适配器。

        Args:
            bot: 所属的 WeChatBot 实例引用。
        """
        self.bot = bot
        # 异步事件循环引用，由 Bot 在 lifespan 阶段启动后注入
        self.main_loop: asyncio.AbstractEventLoop | None = None
        # 缓存 msgid -> 原始帧字典的映射，用于被动回复
        self._req_id_map: LRUCache = LRUCache(capacity=2000)

    @staticmethod
    def _get_str_field(target_dict: Any, keys: list[str]) -> str:
        """从字典中按 key 列表顺序安全抽取非空字符串属性。

        Args:
            target_dict: 目标字典数据。
            keys: 候选键列表。

        Returns:
            提取到的字符串属性值，若未找到则返回空字符串。
        """
        if isinstance(target_dict, dict):
            for k in keys:
                v = target_dict.get(k)
                if v is not None and str(v).strip() != "" and str(v).strip().lower() != "none":
                    return str(v).strip()
        return ""

    def handle_receive(self, data: dict[str, Any]) -> None:
        """接收企业微信长连接推送的原始事件，翻译成归一化消息投递至中枢。

        Args:
            data: 企业微信推送的原始 JSON 字典。
        """
        cmd = data.get("cmd", "")
        headers = data.get("headers", {})
        body = data.get("body", {})

        req_id = headers.get("req_id", "")

        # 1. 采用多级 Fallback 字段抽取关键消息属性，以完美对齐复杂交互
        msg_id = body.get("msgid") or body.get("msg_id") or body.get("message_id") or req_id or ""
        chat_id = body.get("chatid") or body.get("chat_id") or body.get("conversation_id") or ""
        chat_type_raw = body.get("chattype") or body.get("chat_type") or "single"
        msg_type_raw = body.get("msgtype") or body.get("msg_type") or "text"

        logger.info(
            "[BotID: {}] 收到企业微信 SDK 推送消息 -> cmd='{}', msgid='{}', req_id='{}', msg_type='{}'",
            self.bot.bot_id,
            cmd,
            msg_id,
            req_id,
            msg_type_raw,
        )

        # 缓存 msg_id 与原始数据帧，供后续被动回复 reply/reply_media 时直接使用
        if msg_id:
            self._req_id_map[msg_id] = data

        # 确定发送者 ID (from.userid 等多级容错)
        sender_id = body.get("from", {}).get("userid") or body.get("from_userid") or body.get("sender_id") or ""
        session_id = chat_id if chat_type_raw == "group" or chat_id else sender_id

        # 实例化标准归一化消息体
        standard_msg = StandardMessage(
            message_id=msg_id,
            platform="wechat",
            bot_id=self.bot.bot_id,
            chat_type="p2p" if chat_type_raw == "single" else "group",
            session_id=session_id,
            sender_id=sender_id,
        )

        # 0. 优先检测企微模板卡片按钮点击回调事件 (template_card_event)
        event_obj = body.get("event") or body.get("Event") or {}
        card_evt_data = {}
        if isinstance(event_obj, dict):
            card_evt_data = event_obj.get("template_card_event") or event_obj.get("templatecardevent") or event_obj

        event_type = (
            self._get_str_field(card_evt_data, ["eventtype", "event_type", "event"])
            or self._get_str_field(event_obj, ["eventtype", "event_type", "event"])
            or self._get_str_field(body, ["event", "event_type"])
        )

        event_key = (
            self._get_str_field(card_evt_data, ["event_key", "EventKey", "key"])
            or self._get_str_field(event_obj, ["event_key", "EventKey", "key"])
            or self._get_str_field(body, ["event_key", "EventKey", "key"])
        )

        cb_task_id = (
            self._get_str_field(card_evt_data, ["task_id", "taskId"])
            or self._get_str_field(event_obj, ["task_id", "taskId"])
            or self._get_str_field(body, ["task_id", "taskId"])
        )

        is_card_event = (
            event_type in ("template_card_event", "card_button_click")
            or (msg_type_raw == "event" and bool(event_key))
        )

        if is_card_event and event_key:
            logger.info(
                "[BotID: {}] 识别到企微卡片按钮点击回调事件 -> msg_type='{}', event_type='{}', task_id='{}', event_key='{}', sender_id='{}'",
                self.bot.bot_id,
                msg_type_raw,
                event_type,
                cb_task_id,
                event_key,
                sender_id,
            )
            result_text = f"[卡片提交结果] (TaskID: {cb_task_id}) 单选结果: {event_key}" if cb_task_id else f"[卡片提交结果] 单选结果: {event_key}"

            standard_msg.content.append(
                MessageContent(
                    msg_type=MessageType.TEXT,
                    text=result_text,
                )
            )
            self._submit_to_hub(standard_msg)
            return

        # 忽略无具体交互 key 的普通系统事件，避免产生误回复
        if msg_type_raw == "event":
            logger.debug("[BotID: {}] 忽略无具体交互 key 的企微系统事件", self.bot.bot_id)
            return

        # 2. 递归遍历和排重收集包体内所有多模态区块（包括 mixed 图文混排以及各种深层嵌套）
        parts: list[dict[str, Any]] = []
        seen: set[tuple[str, str]] = set()
        self._collect_parts_recursive(body, parts, seen)

        if parts:
            for part in parts:
                part_type = part["type"]
                # 文本
                if part_type == "text":
                    standard_msg.content.append(
                        MessageContent(msg_type=MessageType.TEXT, text=part["text"])
                    )
                # 图片
                elif part_type == "image":
                    minio_url = self._download_and_decrypt_media(
                        url=part["url"],
                        aeskey=part["aeskey"],
                        res_type="image",
                        session_id=session_id,
                    )
                    if minio_url:
                        standard_msg.content.append(
                            MessageContent(msg_type=MessageType.IMAGE, file_url=minio_url)
                        )
                # 音频/语音
                elif part_type in {"voice", "audio"}:
                    minio_url = self._download_and_decrypt_media(
                        url=part["url"],
                        aeskey=part["aeskey"],
                        res_type="audio",
                        session_id=session_id,
                    )
                    if minio_url:
                        standard_msg.content.append(
                            MessageContent(msg_type=MessageType.AUDIO, file_url=minio_url)
                        )
                # 视频
                elif part_type == "video":
                    minio_url = self._download_and_decrypt_media(
                        url=part["url"],
                        aeskey=part["aeskey"],
                        res_type="video",
                        session_id=session_id,
                    )
                    if minio_url:
                        standard_msg.content.append(
                            MessageContent(msg_type=MessageType.VIDEO, file_url=minio_url)
                        )
                # 文件
                elif part_type == "file":
                    file_name = part["filename"] or "file"
                    minio_url = self._download_and_decrypt_media(
                        url=part["url"],
                        aeskey=part["aeskey"],
                        res_type="file",
                        session_id=session_id,
                        file_name=file_name,
                    )
                    if minio_url:
                        standard_msg.content.append(
                            MessageContent(
                                msg_type=MessageType.FILE,
                                file_url=minio_url,
                                file_name=file_name,
                            )
                        )
        else:
            # 兜底转换
            logger.warning(
                "[BotID: {}] 包内未收集到有效媒体部件，进行普通消息类型转化: {}",
                self.bot.bot_id,
                msg_type_raw,
            )
            standard_msg.content.append(
                MessageContent(msg_type=MessageType.TEXT, text=f"[暂不支持的消息类型: {msg_type_raw}]")
            )

        logger.info(
            "[BotID: {}] 投递入站消息，归一化 StandardMessage JSON: {}",
            self.bot.bot_id,
            standard_msg.model_dump_json(indent=2),
        )
        # 通过跨线程安全搭桥投递入站消息给异步路由中枢
        self._submit_to_hub(standard_msg)

    def _collect_parts_recursive(
        self,
        node: Any,
        parts: list[dict[str, Any]],
        seen: set[tuple[str, str]],
        parent_key: str = "",
    ) -> None:
        """深度优先递归提取并排重收集企微推送帧内所有文本和多媒体块。"""
        if isinstance(node, list):
            for item in node:
                self._collect_parts_recursive(item, parts, seen, parent_key)
            return

        if not isinstance(node, dict):
            return

        # 确定类型：使用节点自带的类型，或者父节点的 key (如 "image"、"file") 作为 fallback
        raw_type = node.get("type") or node.get("msgtype") or node.get("content_type") or node.get("item_type") or parent_key
        normalized_type = str(raw_type or "").strip().lower()

        # 1. 段落文本内容提取
        text_val = node.get("content")
        if not text_val and "text" in node and isinstance(node["text"], dict):
            text_val = node["text"].get("content")

        if isinstance(text_val, str) and text_val.strip():
            text_val = text_val.strip()
            # 仅在文本节点类型或无类型时当做文本块
            if normalized_type in {"", "text", "paragraph", "plain"}:
                key = ("text", text_val)
                if key not in seen:
                    seen.add(key)
                    parts.append({"type": "text", "text": text_val})
                return

        # 2. 多媒体资源节点提取
        media_url = node.get("url")
        if isinstance(media_url, str) and media_url.strip():
            media_url = media_url.strip()
            aeskey = node.get("aeskey") or node.get("aes_key") or ""
            filename = node.get("filename") or node.get("name") or ""
            # 如果类型指定为多媒体类型，则直接加入
            if normalized_type in {"image", "file", "video", "voice", "audio"}:
                key = (normalized_type, media_url)
                if key not in seen:
                    seen.add(key)
                    parts.append({
                        "type": normalized_type,
                        "url": media_url,
                        "aeskey": aeskey,
                        "filename": filename,
                    })
                return

        # 递归向下挖掘子字典
        for k, val in node.items():
            self._collect_parts_recursive(val, parts, seen, k)

    def _submit_to_hub(self, msg: StandardMessage) -> None:
        """将归一化消息安全地从同步长连接线程投递至异步事件循环中枢。

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

    def _download_and_decrypt_media(
        self,
        *,
        url: str,
        aeskey: str,
        res_type: str,
        session_id: str,
        file_name: str | None = None,
    ) -> str | None:
        """下载加密媒体资源文件，进行 AES 解密，并转存至本地 MinIO。

        Args:
            url: 媒体文件的加密下载地址。
            aeskey: 资源解密密钥，通常为 Base64 编码。
            res_type: 资源类型，如 "image", "audio", "video", "file"。
            session_id: 发送者或群聊会话 ID。
            file_name: 文件名（用于 file 类型）。

        Returns:
            转存至 MinIO 的统一 URL，若失败则返回 None。
        """
        if not url or not aeskey:
            return None

        try:
            # 1. 下载加密的媒体文件
            headers = {"User-Agent": "Mozilla/5.0"}
            req = urllib.request.Request(url, headers=headers)
            with urllib.request.urlopen(req, timeout=15) as response:
                encrypted_bytes = response.read()

            # 2. 进行 AES-256-CBC 解密
            # 补齐 Base64 padding
            key_pad = len(aeskey) % 4
            if key_pad:
                aeskey += "=" * (4 - key_pad)
            raw_key = base64.b64decode(aeskey)
            iv = raw_key[:16]

            cipher = AES.new(raw_key, AES.MODE_CBC, iv)
            decrypted_bytes = cipher.decrypt(encrypted_bytes)

            # PKCS7 反填充
            pad_len = decrypted_bytes[-1]
            if 1 <= pad_len <= 32:
                decrypted_bytes = decrypted_bytes[:-pad_len]

            # 3. 自适应确定文件后缀和 MIME 类型
            if res_type == "image":
                file_extension = ".png"
                content_type = "image/png"
            elif res_type == "audio":
                file_extension = ".amr"
                content_type = "audio/amr"
            elif res_type == "video":
                file_extension = ".mp4"
                content_type = "video/mp4"
            else:
                if file_name and "." in file_name:
                    file_extension = f".{file_name.split('.')[-1]}"
                else:
                    file_extension = ""
                content_type = "application/octet-stream"

            unique_name = f"{uuid.uuid4()}{file_extension}"
            object_name = f"wechat/{self.bot.bot_id}/{session_id}/{unique_name}"

            # 4. 上传至 MinIO
            minio_url = minio_client.upload_file(
                object_name=object_name,
                data=io.BytesIO(decrypted_bytes),
                length=len(decrypted_bytes),
                content_type=content_type,
            )
            return minio_url

        except Exception as exc:
            logger.error(
                "[BotID: {}] 下载解密或转存微信资源失败 (type='{}'): {}",
                self.bot.bot_id,
                res_type,
                exc,
            )
            return None

    def _get_object_name_from_url(self, file_url: str) -> str:
        """从 MinIO URL 中反向解析对象在存储桶中的真实相对路径。

        Args:
            file_url: 标准文件下载 URL。

        Returns:
            MinIO 存储桶内对象真实路径相对字符串。
        """
        parsed = urlparse(file_url)
        path = parsed.path.lstrip("/")
        # 去掉桶名称前缀以获取桶内实际路径
        bucket_prefix = minio_client.bucket_name + "/"
        if path.startswith(bucket_prefix):
            return path[len(bucket_prefix) :]

        # 容错降级：直接以 '/' 分割掉第一部分（第一部分是 bucket）
        parts = path.split("/", 1)
        if len(parts) > 1:
            return parts[1]
        return path

    def _upload_media_to_wechat(self, file_url: str, res_type: str, file_name: str | None = None) -> str | None:
        """从 MinIO 下载资源，并调用 SDK WSClient 上传临时素材，获取 media_id。

        Args:
            file_url: MinIO 内的媒体资源下载 URL。
            res_type: 资源类型，如 "image", "audio", "video", "file"。
            file_name: 可选文件名。

        Returns:
            微信分配 of media_id，如果失败则返回 None。
        """
        if not file_url:
            return None

        object_name = self._get_object_name_from_url(file_url)

        try:
            # 1. 从 MinIO 下载
            file_stream = minio_client.download_file(object_name=object_name)
            if file_stream is None:
                logger.error(
                    "[BotID: {}] 从 MinIO 读取资源文件失败: {}",
                    self.bot.bot_id,
                    object_name,
                )
                return None

            media_bytes = file_stream.read()

            # 确定文件名
            actual_name = file_name
            if not actual_name:
                if res_type == "image":
                    actual_name = "image.png"
                elif res_type == "audio":
                    actual_name = "voice.amr"
                elif res_type == "video":
                    actual_name = "video.mp4"
                else:
                    actual_name = "file.bin"

            # 2. 跨线程投递到子线程中执行 SDK upload_media
            if self.bot._loop is None or not self.bot._loop.is_running() or self.bot.client is None:
                logger.error("[BotID: {}] WeChatBot SDK Client 未连接，无法执行素材上传。", self.bot.bot_id)
                return None

            # voice 映射
            upload_type = "voice" if res_type == "audio" else res_type

            future = asyncio.run_coroutine_threadsafe(
                self.bot.client.upload_media(
                    media_bytes,
                    type=upload_type,
                    filename=actual_name
                ),
                self.bot._loop
            )

            # 同步阻塞等待分块上传完成，最长等 45s
            upload_result = future.result(timeout=45.0)
            media_id = upload_result.get("media_id")
            return media_id

        except Exception as exc:
            logger.error(
                "[BotID: {}] 上传媒体资源至微信长连接失败: {}",
                self.bot.bot_id,
                exc,
            )
            return None

    def send_message(self, msg: StandardMessage) -> None:
        """将标准出站消息通过 wecom_aibot_sdk 发送给企业微信。

        Args:
            msg: 出站的标准归一化消息体。
        """
        if not msg.content:
            logger.warning("[BotID: {}] 待发送的标准消息内容为空，放弃发送。", self.bot.bot_id)
            return

        logger.info(
            "[BotID: {}] 收到待发送出站消息，StandardMessage JSON: {}",
            self.bot.bot_id,
            msg.model_dump_json(indent=2),
        )

        if self.bot._loop is None or not self.bot._loop.is_running() or self.bot.client is None:
            logger.error("[BotID: {}] WeChatBot SDK Client 未就绪，无法发送消息。", self.bot.bot_id)
            return

        # 检查是否能找到入站时缓存的原始数据帧 (若有且非 event 事件回调，说明是被动回复)
        cached_frame = None
        if msg.message_id:
            raw_frame = self._req_id_map.get(msg.message_id)
            if raw_frame:
                frame_cmd = raw_frame.get("cmd", "")
                frame_msgtype = raw_frame.get("body", {}).get("msgtype", "")
                # 企微规约：aibot_event_callback (事件回调) 无法使用 reply_stream 被动回复，必须通过主动发送接口出站
                if frame_cmd != "aibot_event_callback" and frame_msgtype != "event":
                    cached_frame = raw_frame

        # 遍历标准消息的所有区块，分别进行回复或发送
        # 企业微信对被动回复通道只有一次使用权（一次性应答），故如果存在多个块，仅首个块使用被动回复，后续块全部自动降级使用主动发送
        is_first_reply_sent = False
        for item in msg.content:
            # 确定当前区块是使用被动回复（cached_frame）还是主动发送（None）
            current_frame = None
            if cached_frame and not is_first_reply_sent:
                current_frame = cached_frame
                is_first_reply_sent = True

            # 1. 文本消息
            if item.msg_type == MessageType.TEXT and item.text:
                if current_frame:
                    future = asyncio.run_coroutine_threadsafe(
                        self.bot.client.reply_stream(
                            current_frame,
                            stream_id=uuid.uuid4().hex,
                            content=item.text,
                            finish=True
                        ),
                        self.bot._loop
                    )
                else:
                    future = asyncio.run_coroutine_threadsafe(
                        self.bot.client.send_message(
                            msg.session_id,
                            body={
                                "msgtype": "markdown",
                                "markdown": {"content": item.text},
                            }
                        ),
                        self.bot._loop
                    )
                future.result(timeout=15.0)

            # 2. 多媒体类消息 (图片, 音频, 视频, 普通文件)
            elif item.msg_type in {MessageType.IMAGE, MessageType.AUDIO, MessageType.VIDEO, MessageType.FILE}:
                # 微信类型映射
                res_type_map = {
                    MessageType.IMAGE: "image",
                    MessageType.AUDIO: "audio",
                    MessageType.VIDEO: "video",
                    MessageType.FILE: "file"
                }
                res_type = res_type_map[item.msg_type]
                send_media_type = "voice" if res_type == "audio" else res_type
                file_name = item.file_name or ""

                media_id = self._upload_media_to_wechat(item.file_url, res_type, file_name=file_name)
                if not media_id:
                    logger.error("[BotID: {}] 微信媒体上传失败，跳过该多媒体出站消息模块。", self.bot.bot_id)
                    continue

                if current_frame:
                    # 被动回复媒体卡片
                    future = asyncio.run_coroutine_threadsafe(
                        self.bot.client.reply_media(
                            current_frame,
                            media_type=send_media_type,
                            media_id=media_id,
                            video_title=file_name if send_media_type == "video" else None
                        ),
                        self.bot._loop
                    )
                else:
                    # 主动发送媒体卡片
                    future = asyncio.run_coroutine_threadsafe(
                        self.bot.client.send_media_message(
                            msg.session_id,
                            media_type=send_media_type,
                            media_id=media_id,
                            video_title=file_name if send_media_type == "video" else None
                        ),
                        self.bot._loop
                    )
                future.result(timeout=15.0)

            # 3. 卡片交互消息类型处理 (MessageType.CARD / MessageType.INTERACTIVE)
            elif item.msg_type in {MessageType.CARD, MessageType.INTERACTIVE}:
                wechat_card_body = None
                if item.card_data:
                    wechat_card_body = self._translate_common_card_to_wechat(item.card_data)
                elif item.card_json:
                    if isinstance(item.card_json, dict):
                        wechat_card_body = item.card_json
                    elif isinstance(item.card_json, str):
                        try:
                            wechat_card_body = json.loads(item.card_json)
                        except Exception:
                            wechat_card_body = None

                if not wechat_card_body:
                    logger.warning("[BotID: {}] 无法反归一化解析微信卡片数据，跳过发送。", self.bot.bot_id)
                    continue

                logger.info(
                    "[BotID: {}] 微信适配器成功将公共卡片反归一化翻译为 button_interaction 模板卡片: {}",
                    self.bot.bot_id,
                    wechat_card_body,
                )

                future = asyncio.run_coroutine_threadsafe(
                    self.bot.client.send_message(
                        msg.session_id,
                        body=wechat_card_body,
                    ),
                    self.bot._loop,
                )
                future.result(timeout=15.0)

    def _translate_common_card_to_wechat(self, card_data: Any) -> dict[str, Any]:
        """【反归一化翻译切面】将解耦的公共卡片数据模型 (QuestionCardData) 动态翻译组装为企微 button_interaction 模板卡片 JSON 包体。

        使用 horizontal_content_list 实现优雅的"竖排选项展示"，配合底部简短操作按钮 (button_list)。
        """
        if isinstance(card_data, dict):
            try:
                card_obj = QuestionCardData(**card_data)
            except Exception as exc:
                logger.warning(
                    "[BotID: {}] 尝试将字典转换为 QuestionCardData 异常: {}",
                    self.bot.bot_id,
                    exc,
                )
                return card_data
        elif isinstance(card_data, QuestionCardData):
            card_obj = card_data
        else:
            return {}

        horizontal_content_list: list[dict[str, Any]] = []
        button_list: list[dict[str, Any]] = []

        # 1. 动态填充竖排选项列表 (horizontal_content_list) 与底部短按钮 (button_list)
        for idx, opt in enumerate(card_obj.options):
            if isinstance(opt, str):
                opt_key = chr(65 + idx)
                raw_label = opt
                btn_key = f"{opt_key}: {raw_label}"
            elif isinstance(opt, CardOptionItem):
                opt_key = opt.key or chr(65 + idx)
                raw_label = opt.label
                btn_key = opt.value or opt.label or f"{opt_key}: {raw_label}"
            else:
                continue

            # 整理详情展示（剥离前导 "A: " 或 "A：" 等重复 Key 前缀）
            clean_val = raw_label
            for prefix in (f"{opt_key}: ", f"{opt_key}：", f"{opt_key}."):
                if clean_val.startswith(prefix):
                    clean_val = clean_val[len(prefix) :].strip()
                    break

            # 竖排列表展示
            horizontal_content_list.append(
                {
                    "keyname": opt_key,
                    "value": clean_val,
                }
            )

            # 底部简短按钮组
            button_list.append(
                {
                    "text": f"选 {opt_key}",
                    "style": 1,
                    "key": btn_key,
                }
            )

        # 生成规范且唯一的 task_id（由数字、字母及符号构成，最长128字节）
        task_id = card_obj.card_id or f"task_{uuid.uuid4().hex[:20]}"

        # 清洗 description 中的 markdown 符号，适合企微模板卡片展示
        clean_desc = card_obj.description or ""
        if clean_desc.startswith("**题目：** "):
            clean_desc = clean_desc[len("**题目：** ") :]
        elif clean_desc.startswith("**题目：**"):
            clean_desc = clean_desc[len("**题目：**") :]

        # 2. 组装符合企微极简优化的 button_interaction 模板卡片
        template_card: dict[str, Any] = {
            "card_type": "button_interaction",
            "task_id": task_id,
            "main_title": {
                "title": card_obj.title,
                "desc": clean_desc,
            },
            "horizontal_content_list": horizontal_content_list,
            "button_list": button_list,
        }

        # 3. 封装为完整的发送包体
        return {
            "msgtype": "template_card",
            "template_card": template_card,
        }
