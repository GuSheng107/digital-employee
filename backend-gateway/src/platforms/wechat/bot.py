# -*- coding: utf-8 -*-
"""企业微信 Bot 实例。

基于原生的 websockets 维持与企业微信长连接的网络保活与重连逻辑，
并实现了全双工下的 API 调用（RPC over WebSocket）和媒体资源分片上传逻辑。
"""

import asyncio
import json
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

        # 存储当前正阻塞等待响应的 Futures，key 为 req_id
        self._response_futures: dict[str, asyncio.Future[dict[str, Any]]] = {}

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

    async def call_api(self, cmd: str, body: dict[str, Any], timeout: float = 15.0) -> dict[str, Any]:
        """向企业微信发送 WebSocket 请求包，并等待响应返回（RPC 模式）。

        Args:
            cmd: 命令类型。
            body: 请求体内容。
            timeout: 超时秒数。

        Returns:
            服务端返回的响应包字典。
        """
        if self.ws is None or self._loop is None:
            raise RuntimeError("WebSocket 暂未连接，无法执行接口请求。")

        req_id = str(uuid.uuid4())
        fut = self._loop.create_future()
        self._response_futures[req_id] = fut

        payload = {
            "cmd": cmd,
            "headers": {
                "req_id": req_id
            },
            "body": body
        }

        # 写入发送队列
        await self._send_queue.put(payload)

        try:
            # 阻塞等待响应
            resp = await asyncio.wait_for(fut, timeout=timeout)
            return resp
        except Exception as exc:
            self._response_futures.pop(req_id, None)
            logger.error("[BotID: {}] 长连接接口调用 '{}' 异常或超时 (req_id={}): {}", self.bot_id, cmd, req_id, exc)
            raise

    async def upload_media(self, media_bytes: bytes, filename: str, res_type: str) -> str:
        """分片上传媒体资源到微信，并获取返回的 media_id。

        Args:
            media_bytes: 媒体文件二进制数据。
            filename: 上传的文件名。
            res_type: 资源类型，如 "image", "audio", "video", "file"。

        Returns:
            WeChat 返回的 media_id 字符串。
        """
        import base64
        import hashlib

        md5_val = hashlib.md5(media_bytes).hexdigest()
        total_size = len(media_bytes)

        # 微信临时素材的类型需要映射
        # 支持普通文件（file），图片（image），语音（voice）和视频（video）
        wechat_type = "voice" if res_type == "audio" else res_type

        # 每一片大小设定为 400KB (必须 <= 512KB)
        chunk_size = 400 * 1024
        chunks = []
        for i in range(0, total_size, chunk_size):
            chunks.append(media_bytes[i:i+chunk_size])

        total_chunks = len(chunks)
        logger.info(
            "[BotID: {}] 开始通过长连接分片上传临时素材 (type='{}', name='{}', size={} 字节, 共 {} 分片)",
            self.bot_id,
            wechat_type,
            filename,
            total_size,
            total_chunks
        )

        # 1. 初始化上传
        init_body = {
            "type": wechat_type,
            "filename": filename,
            "total_size": total_size,
            "total_chunks": total_chunks,
            "md5": md5_val
        }
        init_resp = await self.call_api("aibot_upload_media_init", init_body)
        if init_resp.get("errcode", 0) != 0:
            raise RuntimeError(f"素材初始化上传失败: {init_resp.get('errmsg')}")

        upload_id = init_resp.get("body", {}).get("upload_id")
        if not upload_id:
            raise RuntimeError("微信初始化上传响应中未返回 upload_id")

        # 2. 逐片上传
        for idx, chunk in enumerate(chunks):
            base64_data = base64.b64encode(chunk).decode("utf-8")
            chunk_body = {
                "upload_id": upload_id,
                "chunk_index": idx,
                "base64_data": base64_data
            }
            chunk_resp = await self.call_api("aibot_upload_media_chunk", chunk_body)
            if chunk_resp.get("errcode", 0) != 0:
                raise RuntimeError(f"分片 {idx} 上传失败: {chunk_resp.get('errmsg')}")

        # 3. 完成上传并返回 media_id
        finish_body = {
            "upload_id": upload_id
        }
        finish_resp = await self.call_api("aibot_upload_media_finish", finish_body)
        if finish_resp.get("errcode", 0) != 0:
            raise RuntimeError(f"素材上传合并失败: {finish_resp.get('errmsg')}")

        media_id = finish_resp.get("body", {}).get("media_id")
        if not media_id:
            raise RuntimeError("微信完成上传响应中未返回 media_id")

        logger.info(
            "[BotID: {}] 素材长连接上传成功 (upload_id='{}') -> media_id='{}'",
            self.bot_id,
            upload_id,
            media_id
        )
        return media_id

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
            headers = data.get("headers", {})
            errcode = data.get("errcode", 0)
            errmsg = data.get("errmsg", "")

            # 优先检查并完成正在阻塞等待结果的 API 调用 (RPC over WebSocket)
            req_id = headers.get("req_id")
            if req_id and req_id in self._response_futures:
                self._response_futures[req_id].set_result(data)
                continue

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
                }
            }
            if self._send_queue is not None:
                await self._send_queue.put(ping_payload)
