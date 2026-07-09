# -*- coding: utf-8 -*-
"""企业微信消息协议适配器。

负责在企业微信长连接事件 Payload 与全局归一化 StandardMessage 协议之间进行双向翻译。
"""

import asyncio
import concurrent.futures
from collections import OrderedDict
import uuid
from typing import Any

from loguru import logger

from src.core.hub import hub
from src.core.schemas import MessageContent, StandardMessage
from src.platforms.base import BaseAdapter


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
    """企业微信平台双向数据翻译适配器。"""

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
                MessageContent(msg_type="text", text=user_text)
            )
        else:
            # 暂时只支持文本消息，其它类型忽略或转换为提示文本
            logger.warning(
                "[BotID: {}] 暂不支持的企业微信消息类型: {}",
                self.bot.bot_id,
                msg_type,
            )
            standard_msg.content.append(
                MessageContent(msg_type="text", text=f"[暂不支持的消息类型: {msg_type}]")
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

        # 合并所有文本区块，组成待回复内容
        texts = []
        for item in msg.content:
            if item.msg_type == "text" and item.text:
                texts.append(item.text)
            elif item.msg_type == "image":
                texts.append(f"[图片: {item.file_url}]")
            elif item.msg_type == "file":
                file_name = item.file_name or "文件"
                texts.append(f"[文件 ({file_name}): {item.file_url}]")
            else:
                texts.append(f"[{item.msg_type} 消息]")

        full_content = "\n".join(texts)

        # 检查是否能在映射中找到接收时的 req_id (若是对回调的响应)
        cached_req_id = ""
        if msg.message_id:
            cached_req_id = self._req_id_map.get(msg.message_id, "")

        if cached_req_id:
            # 回复模式：使用 aibot_respond_msg
            logger.info(
                "[BotID: {}] 使用回复消息接口回复 (req_id='{}')",
                self.bot.bot_id,
                cached_req_id,
            )
            payload = {
                "cmd": "aibot_respond_msg",
                "headers": {
                    "req_id": cached_req_id
                },
                "body": {
                    "msgtype": "markdown",
                    "markdown": {
                        "content": full_content
                    }
                }
            }
        else:
            # 主动发送模式：使用 aibot_send_msg
            req_id = str(uuid.uuid4())
            logger.info(
                "[BotID: {}] 无匹配接收 req_id，使用主动发送消息接口 (req_id='{}')",
                self.bot.bot_id,
                req_id,
            )
            payload = {
                "cmd": "aibot_send_msg",
                "headers": {
                    "req_id": req_id
                },
                "body": {
                    "chatid": msg.session_id,
                    "chat_type": 1 if msg.chat_type == "p2p" else 2,
                    "msgtype": "markdown",
                    "markdown": {
                        "content": full_content
                    }
                }
            }

        # 调用 Bot 实例上的发送方法
        self.bot.send_websocket_msg(payload)
