# -*- coding: utf-8 -*-
"""飞书 Bot 实例基底。

基于 lark-oapi 长连接维持 WebSocket 网络保活与重连逻辑。所有消息数据翻译及媒体资源置换均交付 FeishuAdapter 处理。
"""

import asyncio
import time
from typing import Any

import lark_oapi as lark
from loguru import logger

from lark_oapi.event.callback.model.p2_card_action_trigger import (
    P2CardActionTrigger,
    P2CardActionTriggerResponse,
)

from src.core.base import BaseBot
from src.platforms.feishu.adapter import FeishuAdapter


class FeishuBot(BaseBot):
    """飞书平台连接维持机器人。

    仅负责网络信道的握手、PING-PONG 心跳保活与自动重连，所有消息收发处理全部收拢至关联适配器中。
    """

    def __init__(self, *, bot_id: str, config: dict[str, Any]) -> None:
        """初始化 FeishuBot 实例。

        Args:
            bot_id: Bot 唯一标识 ID。
            config: 包含 app_id, app_secret 等凭证的配置字典。
        """
        super().__init__(bot_id=bot_id, config=config)
        self.app_id: str = config["app_id"]
        self.app_secret: str = config["app_secret"]

        # 创建飞书底层通用 API 客户端，供给适配器进行文件上传/下载及发信
        self.api_client: lark.Client = (
            lark.Client.builder()
            .app_id(self.app_id)
            .app_secret(self.app_secret)
            .log_level(lark.LogLevel.INFO)
            .build()
        )

        # 实例化专属适配器，绑定当前网络信道实例
        self.adapter: FeishuAdapter = FeishuAdapter(self)

        # 注册飞书事件监听分发器
        self.event_handler: lark.EventDispatcherHandler = (
            lark.EventDispatcherHandler.builder("", "")
            .register_p2_im_message_receive_v1(self._handle_message)
            .register_p2_card_action_trigger(self._handle_card_action)
            .build()
        )

        self.ws_client: lark.ws.Client | None = None
        self._loop: asyncio.AbstractEventLoop | None = None

    def inject_main_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        """注入 FastAPI 主事件循环引用至适配器，支持跨线程安全投递。

        在 FastAPI lifespan 启动阶段调用，此时主事件循环已稳定运行。

        Args:
            loop: FastAPI/Uvicorn 运行中的主异步事件循环实例。
        """
        self.adapter.main_loop = loop
        logger.info("[BotID: {}] 主事件循环已成功注入至适配器。", self.bot_id)

    def _run(self) -> None:
        """运行 Bot 连接维持（阻塞式，在独立子线程中工作）。"""
        self._loop = asyncio.new_event_loop()
        asyncio.set_event_loop(self._loop)

        backoff = 1.0
        while self._is_running:
            try:
                # 强设 lark-oapi 事件循环以支持在独立子线程中并发
                import lark_oapi.ws.client
                lark_oapi.ws.client.loop = self._loop

                logger.info("[BotID: {}] 正在建立飞书 WebSocket 通道连接...", self.bot_id)
                self.ws_client = lark.ws.Client(
                    self.app_id,
                    self.app_secret,
                    event_handler=self.event_handler,
                    log_level=lark.LogLevel.INFO,
                    auto_reconnect=True,
                )

                # ============================================================
                # [Monkey Patch] 修复 lark-oapi <= 1.7.0 WebSocket 长连接模式下
                # CARD 帧被静默丢弃（直接 return）的 SDK Bug。
                #
                # 原始代码 (ws/client.py _handle_data_frame):
                #   elif message_type == MessageType.CARD:
                #       return  # <-- 卡片回调被丢弃，永远不会触发处理器
                #
                # 补丁逻辑：让 CARD 帧与 EVENT 帧走同一条处理路径
                # （_do_without_validation），使注册的 card.action.trigger
                # 回调能被正确触发。
                # ============================================================
                self._patch_ws_card_callback(self.ws_client)

                self.ws_client.start()
                # 正常连接退出（一般不退出，除非 self._is_running 设为 False 且断开连接）
                break
            except Exception as exc:
                if not self._is_running:
                    break
                logger.error(
                    "[BotID: {}] 飞书 WebSocket 信道发生异常: {}, {} 秒后重试...",
                    self.bot_id,
                    exc,
                    backoff,
                )
                time.sleep(backoff)
                backoff = min(backoff * 2, 60.0)

    def _on_stop(self) -> None:
        """停止 WebSocket 连接维持，并关闭关联子线程的事件循环。"""
        if self.ws_client is not None:
            self.ws_client._auto_reconnect = False
            if self._loop is not None and self._loop.is_running():
                # 安全退信，断开底层 Socket 连接
                future = asyncio.run_coroutine_threadsafe(
                    self.ws_client._disconnect(), self._loop
                )
                try:
                    future.result(timeout=3.0)
                except Exception as exc:
                    logger.debug("[BotID: {}] 释放网络连接时发生异常: {}", self.bot_id, exc)

        if self._loop is not None and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)
            logger.info("[BotID: {}] 事件循环已收到安全停止信号。", self.bot_id)

    def _handle_message(self, data: lark.im.v1.P2ImMessageReceiveV1) -> None:
        """接收长连接推送的消息事件，直接交由适配器翻译出站。

        Args:
            data: 原始消息事件体。
        """
        # 直接交由绑定的适配器处理翻译和入站
        self.adapter.handle_receive(data)

    def _handle_card_action(
        self, data: P2CardActionTrigger
    ) -> P2CardActionTriggerResponse:
        """接收卡片交互动作事件，交付适配器处理并归一化出站。

        Args:
            data: 飞书卡片交互动作事件体。

        Returns:
            符合飞书 API 规范的 P2CardActionTriggerResponse 响应。
        """
        return self.adapter.handle_card_action(data)

    @staticmethod
    def _patch_ws_card_callback(ws_client: lark.ws.Client) -> None:
        """对 lark-oapi WebSocket Client 打猴子补丁修复 CARD 帧被丢弃的 Bug。

        lark-oapi <= 1.7.0 中 ws/client.py 的 _handle_data_frame 方法在
        收到 MessageType.CARD 时直接 return，导致卡片交互回调永远无法触发。

        本补丁将 CARD 帧也交由 _do_without_validation 处理，与 EVENT 帧走
        相同的处理路径。
        """
        import base64
        import http
        import time as _time

        from lark_oapi.core.const import UTF_8
        from lark_oapi.core.json import JSON
        from lark_oapi.ws.const import (
            HEADER_BIZ_RT,
            HEADER_MESSAGE_ID,
            HEADER_SEQ,
            HEADER_SUM,
            HEADER_TRACE_ID,
            HEADER_TYPE,
        )
        from lark_oapi.ws.enum import MessageType as _MT
        from lark_oapi.ws.model import Response

        async def _patched_handle_data_frame(frame: Any) -> None:
            """替换后的 _handle_data_frame：让 CARD 帧也走回调处理器。"""

            hs = frame.headers
            msg_id = _get_by_key_safe(hs, HEADER_MESSAGE_ID)
            trace_id = _get_by_key_safe(hs, HEADER_TRACE_ID)
            sum_ = _get_by_key_safe(hs, HEADER_SUM)
            seq = _get_by_key_safe(hs, HEADER_SEQ)
            type_ = _get_by_key_safe(hs, HEADER_TYPE)

            pl = frame.payload
            if int(sum_) > 1:
                pl = ws_client._combine(msg_id, int(sum_), int(seq), pl)
                if pl is None:
                    return

            message_type = _MT(type_)
            logger.debug(
                "[WS-Patch] 收到帧: type={}, msg_id={}, trace_id={}",
                message_type.value, msg_id, trace_id,
            )

            resp = Response(code=http.HTTPStatus.OK)
            try:
                start = int(round(_time.time() * 1000))

                # 核心修复：CARD 帧也走 _do_without_validation
                if message_type in (_MT.EVENT, _MT.CARD):
                    result = ws_client._event_handler._do_without_validation(pl)
                else:
                    return

                end = int(round(_time.time() * 1000))
                header = hs.add()
                header.key = HEADER_BIZ_RT
                header.value = str(end - start)
                if result is not None:
                    resp.data = base64.b64encode(
                        JSON.marshal(result).encode(UTF_8)
                    )
            except Exception as e:
                logger.error(
                    "[WS-Patch] 处理帧异常: type={}, msg_id={}, err={}",
                    message_type.value, msg_id, e,
                )
                resp = Response(code=http.HTTPStatus.INTERNAL_SERVER_ERROR)

            frame.payload = JSON.marshal(resp).encode(UTF_8)
            await ws_client._write_message(frame.SerializeToString())

        def _get_by_key_safe(
            headers: Any, key: str
        ) -> str:
            """安全地从 protobuf headers 中查找键值。"""
            for header in headers:
                if header.key == key:
                    return header.value
            return ""

        # 替换实例方法
        import types
        ws_client._handle_data_frame = types.MethodType(
            lambda self, frame: _patched_handle_data_frame(frame),
            ws_client,
        )
        # 由于 MethodType 包裹的 lambda 不能直接 await，
        # 直接替换为协程函数引用
        ws_client._handle_data_frame = _patched_handle_data_frame

        logger.info(
            "[BotID: WS-Patch] 已成功对 lark.ws.Client._handle_data_frame "
            "打补丁，CARD 帧将正常交由 EventDispatcherHandler 处理。"
        )
