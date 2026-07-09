# -*- coding: utf-8 -*-
"""企业微信 Bot 实例。

基于原生的 websockets 维持与企业微信长连接的网络保活与重连逻辑，
并提供基于 HTTPS 接口的 access_token 获取与临时素材上传组件。
"""

import asyncio
import json
import urllib.request
import uuid
from typing import Any

import websockets
from loguru import logger

from src.core.base import BaseBot
from src.platforms.wechat.adapter import WeChatAdapter


class WeChatBot(BaseBot):
    """企业微信智能连接维持机器人。"""

    def __init__(self, *, bot_id: str, config: dict[str, Any]) -> None:
        """初始化 WeChatBot 实例。

        Args:
            bot_id: Bot 唯一标识 ID。
            config: 包含 app_id (企业微信 BOTID) 和 app_secret (企业微信 Secret) 等的配置字典。
        """
        super().__init__(bot_id=bot_id, config=config)
        self.app_id: str = config["app_id"]
        self.app_secret: str = config["app_secret"]
        self.mode: str = config.get("mode", "test")

        # 实例化专属适配器
        self.adapter: WeChatAdapter = WeChatAdapter(self)

        self.ws: websockets.WebSocketClientProtocol | None = None
        self._loop: asyncio.AbstractEventLoop | None = None
        self._send_queue: asyncio.Queue[dict[str, Any]] | None = None

        # 缓存调用 API 所需的 access_token
        self._access_token: str | None = None
        self._token_expires_at: float = 0

    def inject_main_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """注入 FastAPI 主事件循环引用至适配器。

        Args:
            loop: FastAPI/Uvicorn 运行中的主异步事件循环实例。
        """
        self.adapter.main_loop = loop
        logger.info("[BotID: {}] 主事件循环已成功注入至企业微信适配器。", self.bot_id)

    def _run(self) -> None:
        """运行 Bot 连接维持（阻塞式，在独立子线程中工作）。"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)
        try:
            self._loop.run_until_complete(self._main_co())
        finally:
            self._loop.close()

    def _on_stop(self) -> None:
        """停止 WebSocket 连接维持，并关闭关联子线程的事件循环。"""
        self._is_running = False
        if self._loop is not None and self._loop.is_running():
            if self.ws is not None:
                # 跨线程投递断开连接的任务
                future = asyncio.run_coroutine_threadsafe(self.ws.close(), self._loop)
                try:
                    future.result(timeout=3.0)
                except Exception as exc:
                    logger.debug("[BotID: {}] 释放企业微信长连接异常: {}", self.bot_id, exc)

            self._loop.call_soon_threadsafe(self._loop.stop)
            logger.info("[BotID: {}] 企业微信事件循环已收到停止信号。", self.bot_id)

    def send_websocket_msg(self, payload: dict[str, Any]) -> None:
        """外部线程向长连接发送消息的线程安全接口。

        Args:
            payload: 发送的 JSON 载荷字典。
        """
        if self._loop is None or not self._loop.is_running():
            logger.error("[BotID: {}] 子线程事件循环未启动，放弃发送 WebSocket 消息。", self.bot_id)
            return

        if self._send_queue is None:
            logger.error("[BotID: {}] 发送队列未就绪，放弃发送 WebSocket 消息。", self.bot_id)
            return

        # 跨线程安全地把数据推入子线程 asyncio.Queue
        self._loop.call_soon_threadsafe(self._send_queue.put_nowait, payload)

    def get_access_token(self) -> str | None:
        """获取或刷新调用企业微信 API 所需的 access_token。

        Returns:
            有效的 access_token 字符串，若获取失败则返回 None。
        """
        corpid = self.config.get("corpid")
        if not corpid:
            logger.error(
                "[BotID: {}] 企业微信配置中缺少 corpid，请在 bot.json 中添加该字段以启用 HTTPS 上传临时素材功能。",
                self.bot_id,
            )
            return None

        # 检查是否已有缓存且未过期
        now = asyncio.get_event_loop().time() if self._loop and self._loop.is_running() else 0
        if self._access_token and self._token_expires_at > now:
            return self._access_token

        try:
            url = f"https://qyapi.weixin.qq.com/cgi-bin/gettoken?corpid={corpid}&corpsecret={self.app_secret}"
            req = urllib.request.Request(url)
            with urllib.request.urlopen(req, timeout=10) as response:
                res = json.loads(response.read().decode("utf-8"))

            if res.get("errcode") == 0:
                self._access_token = res["access_token"]
                # 缓存时间设为 7000 秒 (官方有效期为 7200 秒)
                self._token_expires_at = now + 7000 if now > 0 else 7000
                logger.info("[BotID: {}] 成功获取/刷新企业微信 access_token。", self.bot_id)
                return self._access_token
            else:
                logger.error("[BotID: {}] 获取 access_token 失败: {}", self.bot_id, res)
                return None
        except Exception as exc:
            logger.error("[BotID: {}] 请求 gettoken 接口发生异常: {}", self.bot_id, exc)
            return None

    def upload_media_http(self, media_bytes: bytes, filename: str, res_type: str) -> str | None:
        """通过官方 HTTPS 接口，使用 multipart/form-data 方式上传临时素材。

        Args:
            media_bytes: 多媒体原始二进制数据。
            filename: 上传的文件名称（前端展示的文件名）。
            res_type: 媒体文件类型，如 "image", "audio", "video", "file"。

        Returns:
            企业微信返回的 media_id，如果上传失败则返回 None。
        """
        token = self.get_access_token()
        if not token:
            return None

        # 微信支持媒体文件类型，分别有图片（image）、语音（voice）、视频（video）、普通文件（file）
        wechat_type = "voice" if res_type == "audio" else res_type
        url = f"https://qyapi.weixin.qq.com/cgi-bin/media/upload?access_token={token}&type={wechat_type}"

        logger.info(
            "[BotID: {}] 正在通过 HTTPS 上传临时素材 (type='{}', filename='{}', size={} 字节)",
            self.bot_id,
            wechat_type,
            filename,
            len(media_bytes),
        )

        try:
            # 1. 构造 multipart/form-data 分界边界线
            boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"

            # 2. 根据媒体类型确定 Content-Type
            if res_type == "image":
                content_type = "image/png"
            elif res_type == "audio":
                content_type = "audio/amr"
            elif res_type == "video":
                content_type = "video/mp4"
            else:
                content_type = "application/octet-stream"

            # 3. 构造 multipart 消息体字节流
            part_headers = (
                f"--{boundary}\r\n"
                f'Content-Disposition: form-data; name="media"; filename="{filename}"\r\n'
                f"Content-Type: {content_type}\r\n\r\n"
            ).encode("utf-8")

            part_footers = f"\r\n--{boundary}--\r\n".encode("utf-8")

            # 拼接完整的 multipart/form-data 请求体
            body = part_headers + media_bytes + part_footers

            # 4. 发送 POST 请求
            req = urllib.request.Request(
                url,
                data=body,
                headers={
                    "Content-Type": f"multipart/form-data; boundary={boundary}",
                    "Content-Length": str(len(body)),
                },
                method="POST",
            )

            with urllib.request.urlopen(req, timeout=20) as response:
                res = json.loads(response.read().decode("utf-8"))

            if res.get("errcode", 0) == 0:
                media_id = res.get("media_id")
                logger.info(
                    "[BotID: {}] 临时素材 HTTPS 上传成功 -> media_id='{}'",
                    self.bot_id,
                    media_id,
                )
                return media_id
            else:
                logger.error("[BotID: {}] 临时素材 HTTPS 上传失败: {}", self.bot_id, res)
                return None

        except Exception as exc:
            logger.error("[BotID: {}] 临时素材 HTTPS 上传接口请求异常: {}", self.bot_id, exc)
            return None

    async def _main_co(self) -> None:
        """WebSocket 运行和重连的主协程。"""
        backoff = 1.0
        while self._is_running:
            self.ws = None
            try:
                logger.info(
                    "[BotID: {}] 正在建立企业微信 WebSocket 通道连接 (BOTID={})...",
                    self.bot_id,
                    self.app_id,
                )
                ws_url = "wss://openws.work.weixin.qq.com"
                async with websockets.connect(ws_url) as ws:
                    self.ws = ws
                    self._send_queue = asyncio.Queue()
                    backoff = 1.0  # 成功连接后重置退避

                    # 1. 发送订阅请求
                    subscribe_payload = {
                        "cmd": "aibot_subscribe",
                        "headers": {
                            "req_id": str(uuid.uuid4())
                        },
                        "body": {
                            "bot_id": self.app_id,
                            "secret": self.app_secret
                        }
                    }
                    await ws.send(json.dumps(subscribe_payload))
                    logger.info("[BotID: {}] 已发送企业微信订阅包，等待验证...", self.bot_id)

                    # 2. 并发执行接收、发送、心跳
                    await asyncio.gather(
                        self._recv_loop(),
                        self._send_loop(),
                        self._heartbeat_loop(),
                    )
            except Exception as exc:
                if not self._is_running:
                    break
                logger.error(
                    "[BotID: {}] 企业微信长连接异常: {}, {} 秒后重试...",
                    self.bot_id,
                    exc,
                    backoff,
                )
                await asyncio.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    async def _recv_loop(self) -> None:
        """接收 WebSocket 推送消息的协程循环。"""
        if self.ws is None:
            return

        while self._is_running:
            raw_data = await self.ws.recv()
            if not raw_data:
                continue

            try:
                data = json.loads(raw_data)
            except Exception as exc:
                logger.warning("[BotID: {}] 解析企业微信原始消息为 JSON 异常: {}", self.bot_id, exc)
                continue

            cmd = data.get("cmd", "")
            errcode = data.get("errcode", 0)
            errmsg = data.get("errmsg", "")

            # 处理订阅或心跳的响应回包
            if cmd in ("aibot_subscribe_resp", "ping_resp") or "errcode" in data:
                if errcode != 0:
                    logger.error(
                        "[BotID: {}] 企业微信指令 '{}' 响应异常: errcode={}, errmsg='{}'",
                        self.bot_id,
                        cmd,
                        errcode,
                        errmsg,
                    )
                else:
                    logger.debug("[BotID: {}] 收到企业微信系统响应: {}", self.bot_id, data)
                continue

            # 处理消息和事件推送
            if cmd in ("aibot_msg_callback", "aibot_event_callback"):
                body = data.get("body", {})
                event = body.get("event", {})
                event_type = event.get("eventtype", "")

                # 检查是否是被踢连接事件
                if event_type == "disconnected_event":
                    logger.warning("[BotID: {}] 收到企业微信被踢重连信号，WebSocket 物理连接正在断开。", self.bot_id)
                    break

                # 投递给平台消息翻译适配器处理
                self.adapter.handle_receive(data)

    async def _send_loop(self) -> None:
        """出站消息队列推送发送的协程循环。"""
        if self.ws is None or self._send_queue is None:
            return

        while self._is_running:
            payload = await self._send_queue.get()
            try:
                await self.ws.send(json.dumps(payload))
                logger.debug("[BotID: {}] 已发送 WebSocket 包: {}", self.bot_id, payload)
            except Exception as exc:
                logger.error("[BotID: {}] 发送 WebSocket 包失败: {}", self.bot_id, exc)
            finally:
                self._send_queue.task_done()

    async def _heartbeat_loop(self) -> None:
        """心跳保活机制协程，每 25 秒定时执行 PING 指令。"""
        if self.ws is None:
            return

        while self._is_running:
            await asyncio.sleep(25.0)
            ping_payload = {
                "cmd": "ping",
                "headers": {
                    "req_id": str(uuid.uuid4())
                },
                "body": {}
            }
            if self._send_queue is not None:
                await self._send_queue.put(ping_payload)
