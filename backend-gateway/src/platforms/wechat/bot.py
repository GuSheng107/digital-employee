# -*- coding: utf-8 -*-
"""企业微信 Bot 实例。

基于 wecom_aibot_sdk 提供的 WSClient 维护长连接并处理所有的底层事件，
完美兼容官方分块素材上传和事件管理标准。
"""

import asyncio
from typing import Any

from loguru import logger
from wecom_aibot_sdk import WSClient

from src.core.base import BaseBot
from src.platforms.wechat.adapter import WeChatAdapter


class WeChatBot(BaseBot):
    """企业微信智能连接维持机器人（基于官方 SDK 实现）。"""

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

        # 实例化 SDK 长连接 Client
        self.client: WSClient | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

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
        if self._loop is not None and self._loop.is_running() and self.client is not None:
            # 跨线程投递断开连接的任务
            future = asyncio.run_coroutine_threadsafe(self.client.disconnect(), self._loop)
            try:
                future.result(timeout=3.0)
            except Exception as exc:
                logger.debug("[BotID: {}] 释放企业微信 SDK 连接异常: {}", self.bot_id, exc)

            self._loop.call_soon_threadsafe(self._loop.stop)
            logger.info("[BotID: {}] 企业微信事件循环已收到停止信号。", self.bot_id)

    async def _main_co(self) -> None:
        """初始化官方 SDK Client 并启动连接的主协程。"""
        try:
            # 使用官方 SDK 实例托管连接
            self.client = WSClient(
                bot_id=self.app_id,
                secret=self.app_secret,
                heartbeat_interval=30000,  # 30 秒心跳保活
            )

            # 注册长连接事件处理器
            self.client.on("authenticated", self._on_authenticated)
            self.client.on("message", self._on_message)
            self.client.on("event", self._on_message)
            self.client.on("error", self._on_error)

            logger.info(
                "[BotID: {}] 正在通过 wecom_aibot_sdk 建立企业微信长连接通道 (BOTID={})...",
                self.bot_id,
                self.app_id,
            )

            # 开始异步连接
            await self.client.connect()

            # 维持挂起，直到 Bot 停止
            while self._is_running:
                await asyncio.sleep(1.0)

        except Exception as exc:
            logger.error("[BotID: {}] 企业微信 SDK 连接初始化失败: {}", self.bot_id, exc)

    async def _on_authenticated(self, *args: Any, **kwargs: Any) -> None:
        """连接成功订阅验证回调。"""
        logger.info("[BotID: {}] 企业微信长连接已成功建立并订阅验证成功！", self.bot_id)

    async def _on_message(self, frame: dict[str, Any]) -> None:
        """收到原始消息回调。"""
        logger.debug("[BotID: {}] SDK 收到原始消息事件推送: {}", self.bot_id, frame)
        # 传递给适配器处理
        self.adapter.handle_receive(frame)

    async def _on_error(self, error: Exception) -> None:
        """长连接异常回调。"""
        logger.error("[BotID: {}] 企业微信长连接抛出错误: {}", self.bot_id, error)
