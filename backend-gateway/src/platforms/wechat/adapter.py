# -*- coding: utf-8 -*-
"""企业微信消息协议适配器。

负责在企业微信长连接事件 Payload 与全局归一化 StandardMessage 协议之间进行双向翻译，
并接管加密媒体资源解密以及在 MinIO 上的存储寿命周期。
"""

import asyncio
import base64
import concurrent.futures
from collections import OrderedDict
import io
import urllib.request
from urllib.parse import urlparse
import uuid
from typing import Any

from Crypto.Cipher import AES
from loguru import logger

from src.core.hub import hub
from src.core.schemas import MessageContent, MessageType, StandardMessage
from src.platforms.base import BaseAdapter
from src.utils.minio_client import minio_client


class LRUCache(OrderedDict[str, str]):
    """使用 OrderedDict 实现的简易 LRU 缓存，用于存储消息 ID 到请求 ID 的映射。"""

    def __init__(self, capacity: int = 1000) -> None:
        """初始化缓存容量。

        Args:
            capacity: 最大容量。
        """
        super().__init__()
        self.capacity = capacity

    def __setitem__(self, key: str, value: str) -> None:
        """设置缓存值，如果超出容量则弹出最早的项。

        Args:
            key: 消息 ID。
            value: 请求 ID。
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
        # 缓存 msgid -> req_id 的映射，保证回复时携带正确的 req_id
        self._req_id_map: LRUCache = LRUCache(capacity=2000)

    def handle_receive(self, data: dict[str, Any]) -> None:
        """接收企业微信长连接推送的原始事件，翻译成归一化消息投递至中枢。

        Args:
            data: 企业微信推送的原始 JSON 字典。
        """
        cmd = data.get("cmd", "")
        headers = data.get("headers", {})
        body = data.get("body", {})

        req_id = headers.get("req_id", "")
        msg_id = body.get("msgid", "")
        chat_id = body.get("chatid", "")
        chat_type_raw = body.get("chattype", "single")
        msg_type = body.get("msgtype", "text")

        logger.info(
            "[BotID: {}] 收到企业微信原始入站推送 -> cmd='{}', msgid='{}', req_id='{}', msg_type='{}'",
            self.bot.bot_id,
            cmd,
            msg_id,
            req_id,
            msg_type,
        )

        # 缓存 req_id 与 msg_id 的映射关系
        if msg_id and req_id:
            self._req_id_map[msg_id] = req_id

        # 确定会话 ID（单聊为发送者 userid，群聊为群聊 ID）
        sender_id = body.get("from", {}).get("userid", "")
        session_id = chat_id if chat_type_raw == "group" else sender_id

        # 实例化标准归一化消息体
        standard_msg = StandardMessage(
            message_id=msg_id,
            platform="wechat",
            bot_id=self.bot.bot_id,
            chat_type="p2p" if chat_type_raw == "single" else "group",
            session_id=session_id,
            sender_id=sender_id,
        )

        # 1. 文本消息类型转换
        if msg_type == "text":
            user_text = body.get("text", {}).get("content", "")
            standard_msg.content.append(
                MessageContent(msg_type=MessageType.TEXT, text=user_text)
            )

        # 2. 单张图片消息类型转换与解密
        elif msg_type == "image":
            img_data = body.get("image", {})
            minio_url = self._download_and_decrypt_media(
                url=img_data.get("url", ""),
                aeskey=img_data.get("aeskey", ""),
                res_type="image",
                session_id=session_id,
            )
            if minio_url:
                standard_msg.content.append(
                    MessageContent(msg_type=MessageType.IMAGE, file_url=minio_url)
                )

        # 3. 语音消息转换与解密
        elif msg_type == "voice":
            voice_data = body.get("voice", {})
            # 如果有 url 和 aeskey，则尝试进行下载解密
            if voice_data.get("url") and voice_data.get("aeskey"):
                minio_url = self._download_and_decrypt_media(
                    url=voice_data.get("url"),
                    aeskey=voice_data.get("aeskey"),
                    res_type="audio",
                    session_id=session_id,
                )
                if minio_url:
                    standard_msg.content.append(
                        MessageContent(msg_type=MessageType.AUDIO, file_url=minio_url)
                    )
            # 兼容识别出的文本
            text_val = voice_data.get("content") or voice_data.get("text")
            if text_val:
                standard_msg.content.append(
                    MessageContent(msg_type=MessageType.TEXT, text=text_val)
                )

        # 4. 文件消息转换与解密
        elif msg_type == "file":
            file_data = body.get("file", {})
            file_name = file_data.get("filename") or file_data.get("name") or "file"
            minio_url = self._download_and_decrypt_media(
                url=file_data.get("url", ""),
                aeskey=file_data.get("aeskey", ""),
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

        # 5. 视频消息转换与解密
        elif msg_type == "video":
            video_data = body.get("video", {})
            minio_url = self._download_and_decrypt_media(
                url=video_data.get("url", ""),
                aeskey=video_data.get("aeskey", ""),
                res_type="video",
                session_id=session_id,
            )
            if minio_url:
                standard_msg.content.append(
                    MessageContent(msg_type=MessageType.VIDEO, file_url=minio_url)
                )

        # 6. 图文混排消息解析
        elif msg_type == "mixed":
            mixed_data = body.get("mixed", {})
            items = mixed_data.get("msg_item", [])
            for item in items:
                item_type = item.get("type")
                if item_type == "text":
                    text_val = item.get("text", {}).get("content", "")
                    if text_val:
                        standard_msg.content.append(
                            MessageContent(msg_type=MessageType.TEXT, text=text_val)
                        )
                elif item_type == "image":
                    img_data = item.get("image", {})
                    if img_data.get("url") and img_data.get("aeskey"):
                        minio_url = self._download_and_decrypt_media(
                            url=img_data.get("url"),
                            aeskey=img_data.get("aeskey"),
                            res_type="image",
                            session_id=session_id,
                        )
                        if minio_url:
                            standard_msg.content.append(
                                MessageContent(msg_type=MessageType.IMAGE, file_url=minio_url)
                            )

        else:
            logger.warning(
                "[BotID: {}] 暂不支持的企业微信接收消息类型: {}",
                self.bot.bot_id,
                msg_type,
            )
            standard_msg.content.append(
                MessageContent(msg_type=MessageType.TEXT, text=f"[暂不支持的消息类型: {msg_type}]")
            )

        logger.info(
            "[BotID: {}] 投递入站消息，归一化 StandardMessage JSON: {}",
            self.bot.bot_id,
            standard_msg.model_dump_json(indent=2),
        )
        # 通过跨线程安全搭桥投递入站消息给异步路由中枢
        self._submit_to_hub(standard_msg)

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
        """从 MinIO 下载资源，并在长连接子线程中向微信执行分块上传临时素材，获取 media_id。

        Args:
            file_url: MinIO 内的媒体资源下载 URL。
            res_type: 资源类型，如 "image", "audio", "video", "file"。
            file_name: 可选文件名。

        Returns:
            微信分配的 media_id，如果失败则返回 None。
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

            # 2. 直接调用底层的 HTTPS 接口上传临时素材
            media_id = self.bot.upload_media_http(media_bytes, actual_name, res_type)
            return media_id

        except Exception as exc:
            logger.error(
                "[BotID: {}] 上传媒体资源至微信长连接失败: {}",
                self.bot.bot_id,
                exc,
            )
            return None

    def _send_raw_wechat_msg(
        self,
        *,
        msg: StandardMessage,
        msgtype: str,
        content_body: dict[str, Any],
        cached_req_id: str = "",
    ) -> None:
        """组装并发送一条底层的企业微信消息帧。

        Args:
            msg: 标准出站消息。
            msgtype: 微信协议要求的消息类型（如 "markdown", "image", "file" 等）。
            content_body: 消息具体内容字典结构。
            cached_req_id: 若针对某个会话消息响应，可透传该 req_id。
        """
        if cached_req_id:
            # 回复模式：使用 aibot_respond_msg
            logger.info(
                "[BotID: {}] 使用回复消息接口回复分区块 (req_id='{}', type='{}')",
                self.bot.bot_id,
                cached_req_id,
                msgtype,
            )
            payload = {
                "cmd": "aibot_respond_msg",
                "headers": {
                    "req_id": cached_req_id
                },
                "body": {
                    "msgtype": msgtype,
                    **content_body
                }
            }
        else:
            # 主动发送模式：使用 aibot_send_msg
            req_id = str(uuid.uuid4())
            logger.info(
                "[BotID: {}] 无匹配接收 req_id，使用主动发送消息接口 (req_id='{}', type='{}')",
                self.bot.bot_id,
                req_id,
                msgtype,
            )
            payload = {
                "cmd": "aibot_send_msg",
                "headers": {
                    "req_id": req_id
                },
                "body": {
                    "chatid": msg.session_id,
                    "chat_type": 1 if msg.chat_type == "p2p" else 2,
                    "msgtype": msgtype,
                    **content_body
                }
            }

        # 调用 Bot 实例上的发送方法
        self.bot.send_websocket_msg(payload)

    def send_message(self, msg: StandardMessage) -> None:
        """将标准出站消息统一转换并发送给企业微信。

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

        # 检查是否能在映射中找到接收时的 req_id (若是对回调的响应)
        cached_req_id = ""
        if msg.message_id:
            cached_req_id = self._req_id_map.get(msg.message_id, "")

        # 遍历标准消息的所有区块，分别翻译成微信的原生多媒体消息发出去
        for item in msg.content:
            # 1. 文本消息
            if item.msg_type == MessageType.TEXT and item.text:
                self._send_raw_wechat_msg(
                    msg=msg,
                    msgtype="markdown",
                    content_body={"markdown": {"content": item.text}},
                    cached_req_id=cached_req_id
                )

            # 2. 图片消息
            elif item.msg_type == MessageType.IMAGE and item.file_url:
                media_id = self._upload_media_to_wechat(item.file_url, "image")
                if media_id:
                    self._send_raw_wechat_msg(
                        msg=msg,
                        msgtype="image",
                        content_body={"image": {"media_id": media_id}},
                        cached_req_id=cached_req_id
                    )

            # 3. 语音消息
            elif item.msg_type == MessageType.AUDIO and item.file_url:
                media_id = self._upload_media_to_wechat(item.file_url, "audio")
                if media_id:
                    self._send_raw_wechat_msg(
                        msg=msg,
                        msgtype="voice",
                        content_body={"voice": {"media_id": media_id}},
                        cached_req_id=cached_req_id
                    )

            # 4. 视频消息
            elif item.msg_type == MessageType.VIDEO and item.file_url:
                media_id = self._upload_media_to_wechat(item.file_url, "video")
                if media_id:
                    self._send_raw_wechat_msg(
                        msg=msg,
                        msgtype="video",
                        content_body={"video": {"media_id": media_id}},
                        cached_req_id=cached_req_id
                    )

            # 5. 普通文件消息
            elif item.msg_type == MessageType.FILE and item.file_url:
                file_name = item.file_name or "file.bin"
                media_id = self._upload_media_to_wechat(item.file_url, "file", file_name=file_name)
                if media_id:
                    self._send_raw_wechat_msg(
                        msg=msg,
                        msgtype="file",
                        content_body={"file": {"media_id": media_id}},
                        cached_req_id=cached_req_id
                    )
