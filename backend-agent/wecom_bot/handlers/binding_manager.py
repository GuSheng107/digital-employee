from __future__ import annotations

"""管理员绑定管理模块。

管理企微机器人的管理员绑定/解绑流程，包括绑定模式进入、验证码确认、
超时自动解绑以及绑定状态缓存刷新。绑定成功后机器人才能识别管理员会话，
实现消息转发和手动回复等功能。
"""

import asyncio
from typing import Any

from app.db.bot_store import (
    complete_bot_binding,
    get_bot_config,
    make_conversation_key,
    unbind_bot,
)
from wecom_bot.handlers.context import BotContext
from wecom_bot.reply import build_stream_id


class BindingManager:
    """管理员绑定管理器，负责绑定流程的状态机和超时监控。

    处理 "connect mycom" 绑定命令的验证、绑定模式下的消息拦截、
    绑定状态的缓存与刷新，以及绑定超时后的自动解绑。同时提供
    is_personal_chat、is_bound_self_chat 等会话类型判断方法。
    """
    def __init__(self, ctx: BotContext) -> None:
        self._ctx: BotContext = ctx
        self._binding_mode_cache: bool | None = None
        self._binding_entered = asyncio.Event()

    async def handle_bind_command(
        self,
        frame: dict[str, Any],
        raw_context: dict[str, str],
        trace_id: str,
    ) -> bool:
        try:
            bot = get_bot_config(self._ctx.database_path, self._ctx.bot_key)
            if not bot or str(bot.get("bind_status")) != "binding":
                await self._ctx.client.reply_stream(
                    frame,
                    stream_id=build_stream_id(),
                    content="当前不在绑定流程，请先在控制台点击立即绑定。",
                    finish=True,
                )
                return True

            if not self.is_personal_chat(raw_context):
                await self._ctx.client.reply_stream(
                    frame,
                    stream_id=build_stream_id(),
                    content="绑定失败：请由个人会话发送 connect mycom。",
                    finish=True,
                )
                unbind_bot(self._ctx.database_path, self._ctx.bot_key)
                self.refresh_bound_state()
                self._ctx.keepalive.set()
                return True

            complete_bot_binding(
                self._ctx.database_path,
                bot_key=self._ctx.bot_key,
                bound_user_id=raw_context.get("sender_id", ""),
                bound_chat_id=raw_context.get("chat_id", ""),
            )
            self.refresh_bound_state()
            await self._ctx.client.reply_stream(
                frame,
                stream_id=build_stream_id(),
                content="绑定成功",
                finish=True,
            )
            self._ctx.refresh_runtime_settings()
            return True
        except Exception as e:
            self._ctx.logger.exception("绑定过程发生异常", extra={"trace_id": trace_id, "category": "system"})
            await self._ctx.client.reply_stream(
                frame,
                stream_id=build_stream_id(),
                content=f"绑定失败: {str(e)}",
                finish=True,
            )
            return False

    async def handle_binding_mode(
        self,
        frame: dict[str, Any],
        raw_context: dict[str, str],
        *,
        is_text: bool,
    ) -> None:
        if self._ctx.client is None:
            raise RuntimeError("WSClient not initialized")
        if self.is_personal_chat(raw_context):
            content = (
                "绑定流程中，请发送 connect mycom 完成绑定，或取消绑定。"
                if is_text
                else "绑定流程中，请发送文本 connect mycom 完成绑定，不支持非文本消息。"
            )
        else:
            content = "绑定错误 不支持绑定群聊"
        await self._ctx.client.reply_stream(
            frame,
            stream_id=build_stream_id(),
            content=content,
            finish=True,
        )
        unbind_bot(self._ctx.database_path, self._ctx.bot_key)
        self.refresh_bound_state()
        self._ctx.keepalive.set()

    def is_binding_mode(self) -> bool:
        if self._binding_mode_cache is not None:
            return self._binding_mode_cache
        try:
            bot = get_bot_config(self._ctx.database_path, self._ctx.bot_key)
            result = bool(bot and str(bot.get("bind_status")) == "binding")
        except Exception:
            result = False
        self._binding_mode_cache = result
        if result:
            self._binding_entered.set()
        return result

    def invalidate_binding_mode_cache(self) -> None:
        self._binding_mode_cache = None

    def refresh_bound_state(self) -> None:
        bot = get_bot_config(self._ctx.database_path, self._ctx.bot_key)
        if not bot:
            self._ctx.bound_user_id = ""
            self._ctx.bound_chat_id = ""
            self._ctx.bound_chat_name = f"我--{self._ctx.settings.wecom_bot.name}"
            self.invalidate_binding_mode_cache()
            return
        self._ctx.bound_user_id = str(bot.get("bound_user_id") or "").strip()
        self._ctx.bound_chat_id = str(bot.get("bound_chat_id") or "").strip()
        self._ctx.bound_chat_name = f"我--{str(bot.get('name') or self._ctx.settings.wecom_bot.name)}"
        self.invalidate_binding_mode_cache()

    def is_bound_self_chat(self, context: dict[str, str]) -> bool:
        if not self._ctx.bound_chat_id or not self._ctx.bound_user_id:
            return False
        return (
            context.get("chat_id", "") == self._ctx.bound_chat_id
            and context.get("sender_id", "") == self._ctx.bound_user_id
            and self.is_personal_chat(context)
        )

    def is_personal_chat(self, context: dict[str, str]) -> bool:
        sender_id = context.get("sender_id", "")
        chat_id = context.get("chat_id", "")
        if context.get("msg_type") in {"group", "room"}:
            return False
        return bool(sender_id and sender_id != "unknown" and chat_id == sender_id)

    async def watch_binding_timeout(self) -> None:
        binding_timeout_seconds = 180

        while not self._ctx.keepalive.is_set():
            try:
                if self.is_binding_mode():
                    try:
                        await asyncio.wait_for(
                            self._ctx.keepalive.wait(),
                            timeout=binding_timeout_seconds,
                        )
                        return
                    except asyncio.TimeoutError:
                        pass
                    if self.is_binding_mode():
                        self._ctx.logger.info(
                            f"Binding timeout for bot {self._ctx.bot_key} after {binding_timeout_seconds} seconds",
                            extra={"category": "system"},
                        )
                        unbind_bot(self._ctx.database_path, self._ctx.bot_key)
                        self.refresh_bound_state()
                        self._ctx.keepalive.set()
                        return
                    continue

                self._binding_entered.clear()
                try:
                    await asyncio.wait_for(
                        self._binding_entered.wait(),
                        timeout=1.0,
                    )
                except asyncio.TimeoutError:
                    pass
            except asyncio.CancelledError:
                raise
            except Exception:
                self._ctx.logger.exception("Failed while checking binding timeout.", extra={"category": "system"})

    def chat_type_for_context(self, context: dict[str, str]) -> str:
        existing = str(context.get("chat_type") or "").strip().lower()
        if existing in {"group", "room", "user", "single"}:
            return "group" if existing == "room" else existing

        msg_type = str(context.get("msg_type") or "").strip()
        if msg_type in {"group", "room"}:
            return "group"
        if self.is_personal_chat(context):
            return "user"
        chat_id = str(context.get("chat_id") or "").strip()
        sender_id = str(context.get("sender_id") or "").strip()
        if chat_id and sender_id and chat_id != "unknown" and sender_id != "unknown" and chat_id != sender_id:
            return "group"
        return "unknown"
