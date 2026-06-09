from __future__ import annotations

"""企微机器人长连接模式模块。

实现企微机器人的 WebSocket 长连接通信，负责消息路由、AI 回复、
用户反馈处理以及管理员绑定等核心功能。该模块是机器人运行时的
主入口，管理 WebSocket 连接的完整生命周期。
"""

import asyncio
import json
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any
from uuid import uuid4

from agent_runtime import AgentService
from agent_runtime.capabilities import ModelCapability, get_model_capabilities
from agent_runtime.commands import dispatch_system_command, is_command_attempt, is_no_prefix_command, _strip_at_prefix
from agent_runtime.service import sanitize_agent_output
from agent_runtime.stream_orchestrator import StreamAnswerOrchestrator, StreamCallbacks, StreamStatus
from app.chat_store import (
    append_chat_message,
    get_conversation,
    list_active_bot_conversations,
    set_conversation_send_error,
)
from app.config_loader import Settings
from app.database import default_database_path
from app.db.ai_work_store import create_ai_work_item, update_ai_work_item
from app.db.bot_store import get_bot_config, get_bot_runtime_settings, make_conversation_key
from app.db.settings_store import get_platform_settings
from app.db.user_store import get_user_display_name
from app.db.core import connect_database, initialize_database
from app.event_logger import EventLogger, EventCategory, EventLevel, RuntimeEvent
from app.exceptions import DependencyError
from app.logger import get_bot_message_logger, get_logger
from app.db.slot_store import is_chat_locked, wait_for_chat_compress_unlock
from app.db.token_usage_store import get_latest_token_usage
from app.manual_reply_queue import enqueue_manual_reply
from app.process_utils import is_process_running
from app.utils import CST
from app.yaml_config import get_yaml_config
from wecom_bot.frame_store import FrameStore
from wecom_bot.handlers import BindingManager, ManualReplyHandler, MediaHandler
from wecom_bot.handlers.context import BotContext
from wecom_bot.reply import build_stream_id, extract_message_context, extract_text_content

try:
    from wecom_aibot_sdk import WSClient
except ImportError:  # pragma: no cover
    WSClient = None  # type: ignore[assignment]


_FEEDBACK_ID_KEYS = {
    "id",
    "msgid",
    "msg_id",
    "messageid",
    "message_id",
    "feedbackid",
    "feedback_id",
}
_FEEDBACK_RESULT_KEYS = {
    "result",
    "feedback_result",
    "feedbackresult",
    "action",
    "type",
}
_FEEDBACK_REASON_KEYS = {
    "reason",
    "feedback_reason",
    "feedbackreason",
    "reason_text",
    "reasontext",
    "feedback_reason_text",
    "feedbackreasontext",
    "comment",
    "comments",
    "remark",
    "remarks",
    "description",
    "desc",
    "detail",
    "details",
    "text",
    "content",
}
_FEEDBACK_RESULT_ALIASES = {
    "useful": "useful",
    "like": "useful",
    "good": "useful",
    "yes": "useful",
    "1": "useful",
    "true": "useful",
    "useless": "useless",
    "unuseful": "useless",
    "dislike": "useless",
    "bad": "useless",
    "no": "useless",
    "0": "useless",
    "false": "useless",
}
_WECOM_FEEDBACK_TYPE_MAP: dict[int, str] = {
    2: "useless",
    3: "useful",
}
_WECOM_INACCURATE_REASON_MAP: dict[int, str] = {
    1: "与问题无关",
    2: "内容不完整",
    3: "内容有错误",
    4: "数据分析错误",
}


def _as_dict(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _normalize_payload_key(key: Any) -> str:
    return str(key).replace("_", "").replace("-", "").lower()


def _find_string_field(node: Any, keys: set[str], *, max_depth: int = 0, _depth: int = 0) -> str:
    if _depth > max_depth:
        return ""
    if isinstance(node, dict):
        normalized = {_normalize_payload_key(key): key for key in node}
        for key in keys:
            original = normalized.get(_normalize_payload_key(key))
            if original is None:
                continue
            value = node.get(original)
            if value is not None and not isinstance(value, (dict, list)):
                text = str(value).strip()
                if text:
                    return text
        if _depth < max_depth:
            for value in node.values():
                found = _find_string_field(value, keys, max_depth=max_depth, _depth=_depth + 1)
                if found:
                    return found
    elif isinstance(node, list) and _depth < max_depth:
        for value in node:
            found = _find_string_field(value, keys, max_depth=max_depth, _depth=_depth + 1)
            if found:
                return found
    return ""


def _compact_feedback_payload(value: Any, *, _depth: int = 0) -> Any:
    if _depth > 4:
        return "<truncated>"
    if isinstance(value, dict):
        return {
            str(key)[:80]: _compact_feedback_payload(item, _depth=_depth + 1)
            for key, item in list(value.items())[:40]
        }
    if isinstance(value, list):
        return [_compact_feedback_payload(item, _depth=_depth + 1) for item in value[:20]]
    if isinstance(value, str):
        return value[:1200]
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)[:1200]


def _feedback_payload_metadata(
    body: dict[str, Any],
    event: dict[str, Any],
    feedback: dict[str, Any],
) -> dict[str, Any]:
    return {
        "body_keys": [str(key) for key in body.keys()],
        "event_keys": [str(key) for key in event.keys()],
        "feedback_keys": [str(key) for key in feedback.keys()],
        "event": _compact_feedback_payload(event),
        "feedback": _compact_feedback_payload(feedback),
    }


def _extract_feedback_event_fields(frame: dict[str, Any]) -> dict[str, Any]:
    body = _as_dict(frame.get("body") if isinstance(frame, dict) else {})
    event = _as_dict(body.get("event"))
    feedback_event = _as_dict(event.get("feedback_event"))
    feedback = _as_dict(event.get("feedback")) or feedback_event

    msg_id = (
        _find_string_field(feedback_event, _FEEDBACK_ID_KEYS)
        or _find_string_field(feedback, _FEEDBACK_ID_KEYS)
        or _find_string_field(event, _FEEDBACK_ID_KEYS)
        or _find_string_field(body, _FEEDBACK_ID_KEYS)
    )

    wecom_type = feedback_event.get("type")
    result_from_type = _WECOM_FEEDBACK_TYPE_MAP.get(int(wecom_type)) if isinstance(wecom_type, (int, float)) and int(wecom_type) in _WECOM_FEEDBACK_TYPE_MAP else ""

    result_raw = (
        _find_string_field(feedback_event, _FEEDBACK_RESULT_KEYS)
        or _find_string_field(feedback, _FEEDBACK_RESULT_KEYS)
        or _find_string_field(event, _FEEDBACK_RESULT_KEYS)
        or _find_string_field(body, _FEEDBACK_RESULT_KEYS)
    )
    result_from_alias = _FEEDBACK_RESULT_ALIASES.get(result_raw.strip().lower(), "")
    result = result_from_type or result_from_alias

    reason_raw = ""
    inaccurate_reasons: list[str] = []
    if result == "useless":
        reason_raw = (
            _find_string_field(feedback_event, _FEEDBACK_REASON_KEYS)
            or _find_string_field(feedback, _FEEDBACK_REASON_KEYS)
            or _find_string_field(event, _FEEDBACK_REASON_KEYS)
        )
        raw_list = feedback_event.get("inaccurate_reason_list")
        if isinstance(raw_list, list):
            for code in raw_list:
                label = _WECOM_INACCURATE_REASON_MAP.get(int(code) if isinstance(code, (int, float)) else 0)
                if label:
                    inaccurate_reasons.append(label)

    reason_parts: list[str] = []
    if inaccurate_reasons:
        reason_parts.append("、".join(inaccurate_reasons))
    if reason_raw:
        reason_parts.append(reason_raw)
    reason = "；".join(reason_parts) if result == "useless" else ""

    raw_chat_id = (
        _find_string_field(
            body,
            {"chatid", "chat_id", "conversationid", "conversation_id", "roomid", "room_id"},
            max_depth=2,
        )
    )
    user_id = (
        _find_string_field(
            body,
            {"userid", "user_id", "from", "senderid", "sender_id", "fromuserid", "from_userid"},
            max_depth=3,
        )
    )
    return {
        "body": body,
        "event": event,
        "feedback": feedback,
        "msg_id": msg_id,
        "result_raw": result_raw or str(wecom_type or ""),
        "result": result,
        "reason_raw": reason_raw,
        "reason": reason,
        "raw_chat_id": raw_chat_id,
        "user_id": user_id,
        "payload_metadata": _feedback_payload_metadata(body, event, feedback),
    }


class AgentLongConnectionBot:
    """企微机器人长连接主类。

    管理 WebSocket 连接的完整生命周期，包括认证、消息接收与路由、
    AI Agent 调度、用户反馈处理以及管理员绑定状态维护。该类协调
    BindingManager、MediaHandler、ManualReplyHandler 等子模块，
    实现文本/非文本消息的统一处理和并发控制。
    """

    def __init__(
        self,
        settings: Settings,
        parent_pid: int | None = None,
        project_root: Path | None = None,
        bot_key: str = "",
    ) -> None:
        self.settings = settings
        self.parent_pid = parent_pid
        self.bot_key = bot_key
        self.project_root = project_root.resolve() if project_root is not None else Path.cwd()
        self.database_path = default_database_path(self.project_root)
        self.logger = get_logger("wecom_bot.long_connection")
        self.bot_message_logger = get_bot_message_logger()
        self.agent_service = AgentService(settings, project_root=self.project_root)
        self._client: Any | None = None
        self._keepalive = asyncio.Event()
        self._parent_watch_task: asyncio.Task[None] | None = None
        self._manual_reply_task: asyncio.Task[None] | None = None
        self._binding_timeout_task: asyncio.Task[None] | None = None
        self._active_requests = 0
        self._request_lock = asyncio.Lock()
        self._authenticated = asyncio.Event()
        self._fatal_error = asyncio.Event()
        self._startup_broadcast_sent = False
        self._bound_user_id = ""
        self._bound_chat_id = ""
        self._bound_chat_name = f"我的BOT【{self.settings.wecom_bot.name}】"
        self._awaiting_exit_confirm = False
        self._frame_store = FrameStore()
        self._event_logger = EventLogger(self.database_path, logger=self.logger)
        self._ctx = BotContext(
            database_path=self.database_path,
            project_root=self.project_root,
            bot_key=self.bot_key,
            logger=self.logger,
            bot_message_logger=self.bot_message_logger,
            get_client=lambda: self._client,
            get_settings=lambda: self.settings,
            get_bound_chat_id=lambda: self._bound_chat_id,
            get_bound_user_id=lambda: self._bound_user_id,
            get_bound_chat_name=lambda: self._bound_chat_name,
            get_keepalive=lambda: self._keepalive,
            get_frame_store=lambda: self._frame_store,
            get_agent_service=lambda: self.agent_service,
            set_bound_chat_id=lambda v: setattr(self, '_bound_chat_id', v),
            set_bound_user_id=lambda v: setattr(self, '_bound_user_id', v),
            set_bound_chat_name=lambda v: setattr(self, '_bound_chat_name', v),
            log_event=self._event_logger.log_event,
            record_bot_message=self._record_bot_message,
            record_user_message=self._record_user_message,
            send_ai_reply_message=self._send_ai_reply_message,
            format_local_time=self._format_local_message_time,
            handle_conversation_send_failure=self._handle_conversation_send_failure,
            refresh_runtime_settings=self._refresh_runtime_settings,
            frame_req_id=self._frame_req_id,
            send_media_asset=lambda **kw: self._media_handler.send_media_asset(**kw),
            is_size_limit_exceeded=lambda mt, sz: self._media_handler.is_size_limit_exceeded(mt, sz),
            send_message_with_retry=self._send_message_with_retry,
        )
        self._media_handler = MediaHandler(self._ctx)
        self._binding_manager = BindingManager(self._ctx)
        self._manual_reply_handler = ManualReplyHandler(self._ctx)
        self._binding_manager.refresh_bound_state()

    async def run(self) -> None:
        if WSClient is None:
            raise DependencyError(
                "wecom_aibot_sdk is not installed. Install requirements.txt before starting the bot."
            )

        try:
            self._client = WSClient(
                bot_id=self.settings.wecom_bot.bot_id,
                secret=self.settings.wecom_bot.secret,
                ws_url=self.settings.wecom_bot.websocket_url,
                reconnect_interval=self.settings.wecom_bot.reconnect_interval_ms,
                heartbeat_interval=self.settings.wecom_bot.heartbeat_interval_ms,
            )
            self._register_handlers()

            await self._client.connect()
            authenticated = await self._wait_for_authenticated()
            
            if self._fatal_error.is_set():
                self.logger.critical("检测到致命错误，程序将终止", extra={"category": "bot"})
                return
                
            if self.parent_pid is not None:
                self._parent_watch_task = asyncio.create_task(self._watch_parent_process())
            self._manual_reply_task = asyncio.create_task(self._manual_reply_handler.watch_manual_replies())
            self._binding_timeout_task = asyncio.create_task(self._binding_manager.watch_binding_timeout())
            if authenticated:
                await self._send_startup_broadcast_if_needed()
            
            keepalive_task = asyncio.create_task(self._keepalive.wait())
            fatal_task = asyncio.create_task(self._fatal_error.wait())
            done, pending = await asyncio.wait(
                [keepalive_task, fatal_task],
                return_when=asyncio.FIRST_COMPLETED
            )
            
            for task in pending:
                task.cancel()
                
            if self._fatal_error.is_set():
                self.logger.critical("运行过程中检测到致命错误，程序将终止", extra={"category": "bot"})
        except asyncio.CancelledError:
            raise
        except Exception:
            self.logger.exception("Long connection bot crashed.", extra={"category": "bot"})
            raise
        finally:
            if self._parent_watch_task is not None:
                self._parent_watch_task.cancel()
                try:
                    await self._parent_watch_task
                except asyncio.CancelledError:
                    pass
            if self._manual_reply_task is not None:
                self._manual_reply_task.cancel()
                try:
                    await self._manual_reply_task
                except asyncio.CancelledError:
                    pass
            if self._binding_timeout_task is not None:
                self._binding_timeout_task.cancel()
                try:
                    await self._binding_timeout_task
                except asyncio.CancelledError:
                    pass
            await self.stop()

    async def stop(self) -> None:
        if self._client is not None:
            try:
                await asyncio.wait_for(self._client.disconnect(), timeout=5)
            except asyncio.TimeoutError:
                pass
            except asyncio.CancelledError:
                pass
            except Exception:
                self.logger.exception("Failed while disconnecting WeCom bot.", extra={"category": "bot"})
            finally:
                self._client = None

    def _register_handlers(self) -> None:
        if self._client is None:
            raise RuntimeError("WSClient not initialized")
        self._client.on("authenticated", self._on_authenticated)
        self._client.on("message", self._on_message)
        self._client.on("event.enter_chat", self._on_enter_chat)
        self._client.on("event.feedback_event", self._on_feedback_event)
        self._client.on("error", self._on_error)

    async def _on_error(self, error: Exception) -> None:
        self.logger.error("WebSocket client error: %s", error, extra={"category": "network"})
        error_str = str(error).lower()
        if "ssl" in error_str and "certificate" in error_str or "certificate_verify_failed" in error_str:
            self.logger.critical("检测到SSL证书验证失败，这是致命错误，程序将终止", extra={"category": "network"})
            self._fatal_error.set()
            self._keepalive.set()

    async def _on_authenticated(self, *_args: Any, **_kwargs: Any) -> None:
        self._authenticated.set()
        self.logger.info("WeCom bot subscription authenticated.", extra={"category": "bot"})

    async def _on_feedback_event(self, frame: dict[str, Any]) -> None:
        fields = _extract_feedback_event_fields(frame)
        body = fields["body"]
        event = fields["event"]
        msg_id = fields["msg_id"]
        result_raw = fields["result_raw"]
        result = fields["result"]
        reason_raw = fields["reason_raw"]
        reason = fields["reason"]
        raw_chat_id = fields["raw_chat_id"]
        user_id = fields["user_id"]
        payload_metadata = fields["payload_metadata"]

        if not msg_id or result not in {"useful", "useless"}:
            self._log_feedback_system_event(
                trace_id=msg_id or str(uuid4()),
                message="反馈事件无效",
                detail=json.dumps(
                    {
                        "msg_id": msg_id,
                        "raw_result": result_raw,
                        "body_preview": json.dumps(body, ensure_ascii=False)[:1000],
                        "payload_metadata": payload_metadata,
                    },
                    ensure_ascii=False,
                ),
                level=EventLevel.WARNING,
            )
            self.logger.warning(
                "Invalid feedback event: msg_id=%s result=%s body=%s",
                msg_id or "<empty>",
                result_raw or "<empty>",
                json.dumps(body, ensure_ascii=False)[:500],
                extra={"category": "message"},
            )
            return

        raw_ctx = extract_message_context(frame)
        raw_chat_id = raw_chat_id or str(raw_ctx.get("chat_id") or "").strip()
        user_id = user_id or str(raw_ctx.get("sender_id") or "").strip()
        bot_key = self.bot_key
        if raw_chat_id and str(raw_ctx.get("chat_id") or "").strip() in {"", "unknown", str(raw_ctx.get("sender_id") or "").strip()}:
            raw_ctx["chat_id"] = raw_chat_id
        if user_id and str(raw_ctx.get("sender_id") or "").strip() in {"", "unknown"}:
            raw_ctx["sender_id"] = user_id
        try:
            feedback_ctx = self._conversation_context(raw_ctx)
        except Exception:
            self.logger.exception(
                "Failed to normalize feedback event context",
                extra={"category": "system", "msg_id": msg_id},
            )
            feedback_ctx = dict(raw_ctx)
            feedback_ctx["chat_id"] = raw_chat_id or str(raw_ctx.get("chat_id") or "unknown")
            feedback_ctx["bot_key"] = bot_key
        chat_id = str(feedback_ctx.get("chat_id") or raw_chat_id or "unknown").strip()

        self._log_feedback_system_event(
            trace_id=msg_id,
            message="反馈事件已接收",
            detail=json.dumps(
                {
                    "msg_id": msg_id,
                    "chat_id": chat_id,
                    "raw_chat_id": raw_chat_id,
                    "bot_key": bot_key,
                    "user_id": user_id,
                    "result": result,
                    "reason": reason,
                    "payload_metadata": payload_metadata,
                },
                ensure_ascii=False,
            ),
        )

        from app.db.feedback_store import save_feedback

        try:
            save_feedback(
                self.database_path,
                msg_id=msg_id,
                chat_id=chat_id,
                bot_key=bot_key,
                user_id=user_id,
                result=result,
                reason=reason,
                metadata_json=json.dumps(
                    {
                        "source": "user",
                        "eventtype": str(event.get("eventtype") or "") if isinstance(event, dict) else "",
                        "raw_result": result_raw,
                        "raw_reason": reason_raw,
                        "raw_chat_id": raw_chat_id,
                        "payload": payload_metadata,
                    },
                    ensure_ascii=False,
                ),
            )
        except Exception:
            self._log_feedback_system_event(
                trace_id=msg_id,
                message="反馈事件入库失败",
                detail=json.dumps(
                    {"msg_id": msg_id, "chat_id": chat_id, "bot_key": bot_key, "result": result},
                    ensure_ascii=False,
                ),
                level=EventLevel.ERROR,
            )
            self.logger.exception(
                "Failed to record feedback event",
                extra={"category": "message", "msg_id": msg_id, "result": result},
            )
            return

        self._log_feedback_system_event(
            trace_id=msg_id,
            message="反馈事件已入库",
            detail=json.dumps(
                {"msg_id": msg_id, "chat_id": chat_id, "bot_key": bot_key, "user_id": user_id, "result": result, "reason": reason},
                ensure_ascii=False,
            ),
        )
        self.logger.info(
            f"Feedback recorded: {result} for msg {msg_id}",
            extra={"category": "message", "msg_id": msg_id, "result": result},
        )
        if result == "useless":
            await self._check_feedback_alert(chat_id=chat_id, bot_key=bot_key, trace_id=msg_id)

    def _log_feedback_system_event(
        self,
        *,
        trace_id: str,
        message: str,
        detail: str,
        level: EventLevel = EventLevel.INFO,
    ) -> None:
        try:
            self._event_logger.emit(
                RuntimeEvent(
                    trace_id=trace_id,
                    source="feedback_event",
                    message=message,
                    detail=detail,
                    level=level,
                    category=EventCategory.SYSTEM,
                )
            )
        except Exception:
            self.logger.exception(
                "Failed to persist feedback system event.",
                extra={"trace_id": trace_id, "category": "system"},
            )

    async def _check_feedback_alert(self, *, chat_id: str, bot_key: str, trace_id: str) -> None:
        cfg = get_yaml_config(self.project_root).as_dict().get("feedback_alert", {})
        if not bool(cfg.get("enabled", False)):
            return
        if not self._bound_chat_id:
            self._log_feedback_system_event(
                trace_id=trace_id,
                message="反馈告警跳过：管理员未绑定",
                detail=json.dumps({"chat_id": chat_id, "bot_key": bot_key}, ensure_ascii=False),
                level=EventLevel.WARNING,
            )
            return

        threshold = self._positive_config_int(cfg.get("threshold"), 3)
        window_minutes = self._positive_config_int(cfg.get("window_minutes"), 60)
        cooldown_minutes = self._positive_config_int(cfg.get("cooldown_minutes"), 30)

        from app.db.feedback_store import (
            count_recent_useless_feedbacks,
            get_recent_useless_feedback_context,
            record_alert_sent,
            should_send_alert,
        )

        with connect_database(self.database_path) as conn:
            count = count_recent_useless_feedbacks(
                conn,
                chat_id=chat_id,
                bot_key=bot_key,
                window_minutes=window_minutes,
            )
            if count < threshold:
                return
            if not should_send_alert(
                conn,
                chat_id=chat_id,
                bot_key=bot_key,
                cooldown_minutes=cooldown_minutes,
            ):
                return

        context = get_recent_useless_feedback_context(
            self.database_path,
            chat_id=chat_id,
            bot_key=bot_key,
            window_minutes=window_minutes,
            limit=5,
        )
        message = self._build_feedback_alert_message(
            chat_id=chat_id,
            bot_key=bot_key,
            count=count,
            threshold=threshold,
            window_minutes=window_minutes,
            context=context,
        )
        metadata = {
            "count": count,
            "threshold": threshold,
            "window_minutes": window_minutes,
            "cooldown_minutes": cooldown_minutes,
            "admin_chat_id": self._bound_chat_id,
            "context": context,
        }
        with connect_database(self.database_path) as conn:
            record_alert_sent(
                conn,
                chat_id=chat_id,
                bot_key=bot_key,
                threshold=threshold,
                window_minutes=window_minutes,
                feedback_count=count,
                metadata=metadata,
            )

        try:
            await self._send_message_with_retry(
                self._bound_chat_id,
                {"msgtype": "markdown", "markdown": {"content": message}},
                trace_id=trace_id,
            )
            self._log_feedback_system_event(
                trace_id=trace_id,
                message="反馈告警已通知管理员",
                detail=json.dumps(
                    {"chat_id": chat_id, "bot_key": bot_key, "admin_chat_id": self._bound_chat_id, "count": count},
                    ensure_ascii=False,
                ),
            )
        except Exception as exc:
            self._log_feedback_system_event(
                trace_id=trace_id,
                message="反馈告警通知管理员失败",
                detail=json.dumps(
                    {"chat_id": chat_id, "bot_key": bot_key, "admin_chat_id": self._bound_chat_id, "error": str(exc)},
                    ensure_ascii=False,
                ),
                level=EventLevel.ERROR,
            )
            self.logger.exception(
                "Failed to send feedback alert",
                extra={"category": "network", "chat_id": chat_id, "bot_key": bot_key},
            )

    @staticmethod
    def _positive_config_int(value: Any, default: int) -> int:
        try:
            parsed = int(value)
        except (TypeError, ValueError):
            return default
        return parsed if parsed > 0 else default

    def _build_feedback_alert_message(
        self,
        *,
        chat_id: str,
        bot_key: str,
        count: int,
        threshold: int,
        window_minutes: int,
        context: dict[str, Any],
    ) -> str:
        chat = context.get("chat") if isinstance(context.get("chat"), dict) else {}
        chat_name = str(chat.get("display_name") or chat.get("chat_name") or chat_id)
        bot_name = str(context.get("bot_name") or self.settings.wecom_bot.name or bot_key)
        lines = [
            "**Bot 反馈告警**",
            "",
            f"> Bot：{self._markdown_line(bot_name)}",
            f"> 会话：{self._markdown_line(chat_name)}",
            f"> 时间窗口：过去 {window_minutes} 分钟",
            f"> 无用反馈：{count} / {threshold}",
            "",
            "最近无用反馈上下文：",
        ]
        items = context.get("items") if isinstance(context.get("items"), list) else []
        if not items:
            lines.append("- 未找到可展示的上下文")
        for index, item in enumerate(items[:5], start=1):
            question = self._markdown_line(str(item.get("question") or "未匹配到用户问题"), limit=180)
            answer = self._markdown_line(str(item.get("answer") or "未匹配到 Bot 回复"), limit=260)
            reason = self._markdown_line(str(item.get("reason") or ""), limit=180)
            created_at = self._markdown_line(str(item.get("created_at") or ""))
            user_id = self._markdown_line(str(item.get("user_id") or ""))
            lines.extend(
                [
                    f"{index}. {created_at} 用户：{user_id or '-'}",
                    f"   - 问题：{question}",
                    f"   - 回复：{answer}",
                ]
            )
            if reason:
                lines.append(f"   - 反馈原因：{reason}")
        lines.extend(["", "请检查该会话的 Bot 回复质量，必要时介入处理。"])
        return "\n".join(lines)

    @staticmethod
    def _markdown_line(value: str, *, limit: int = 120) -> str:
        text = " ".join(str(value or "").split())
        if len(text) > limit:
            text = text[:limit] + "..."
        return text.replace("|", "\\|")

    async def _on_message(self, frame: dict[str, Any]) -> None:
        trace_id = str(uuid4())
        body = frame.get("body", {}) if isinstance(frame.get("body"), dict) else {}
        msgtype = str(body.get("msgtype", "unknown") or "unknown").strip().lower()
        # 过滤掉一些可能是系统通知的消息，减少日志量
        # 只记录业务相关的消息类型
        silent_msgtypes = {"unknown"}
        should_log = msgtype not in silent_msgtypes
        
        if should_log:
            try:
                self._event_logger.message_event(
                    trace_id=trace_id,
                    message=f"message event received msgtype={msgtype}",
                    detail=f"body_keys={list(body.keys())[:20]}",
                )
            except Exception:
                self.logger.exception("Failed to write message_router log.", extra={"category": "data"})

        try:
            raw_ctx = extract_message_context(frame)
            chat_id_for_frame = str(raw_ctx.get("chat_id") or "").strip()
            self._store_frame(trace_id, frame, chat_id=chat_id_for_frame)
            if msgtype == "text":
                await self._on_text_message(frame, trace_id_override=trace_id)
            else:
                await self._on_non_text_message(frame, trace_id_override=trace_id)
        except Exception as exc:
            self.logger.exception(
                "Failed to route message event.",
                extra={"trace_id": trace_id, "category": "message"},
            )
            self._event_logger.emit(RuntimeEvent(
                trace_id=trace_id,
                source="message_router",
                category=EventCategory.SYSTEM,
                message=f"message route failed msgtype={msgtype} err={exc}",
                level=EventLevel.ERROR,
            ))

    async def _wait_for_authenticated(self) -> bool:
        try:
            auth_task = asyncio.create_task(self._authenticated.wait())
            fatal_task = asyncio.create_task(self._fatal_error.wait())
            done, pending = await asyncio.wait(
                [auth_task, fatal_task],
                timeout=15,
                return_when=asyncio.FIRST_COMPLETED
            )
            for task in pending:
                task.cancel()
            if self._fatal_error.is_set():
                self.logger.critical("在等待认证过程中检测到致命错误", extra={"category": "bot"})
                return False
            if self._authenticated.is_set():
                return True
            self.logger.warning(
                "Timed out waiting for authenticated event; startup broadcast skipped.",
                extra={"category": "bot"},
            )
            return False
        except asyncio.TimeoutError:
            self.logger.warning(
                "Timed out waiting for authenticated event; startup broadcast skipped.",
                extra={"category": "bot"},
            )
            return False

    async def _send_startup_broadcast_if_needed(self) -> None:
        if self._startup_broadcast_sent:
            return
        if not self._bound_chat_id:
            return
        bot = get_bot_config(self.database_path, self.bot_key)
        startup_text = str(bot.get("startup_text", "") or "").strip() if bot else ""
        if not startup_text:
            self._startup_broadcast_sent = True
            return

        conversations = list_active_bot_conversations(
            bot_key=self.bot_key,
            database_path=self.database_path,
        )
        for conversation in conversations:
            if self._should_skip_startup_broadcast(conversation):
                continue
            external_chat_id = str(conversation.get("external_chat_id") or "").strip()
            conversation_chat_id = str(conversation.get("chat_id") or "").strip()
            if not external_chat_id or not conversation_chat_id:
                continue
            chat_name = str(
                conversation.get("display_name")
                or conversation.get("chat_name")
                or external_chat_id
            ).strip() or external_chat_id
            enqueue_manual_reply(
                chat_id=external_chat_id,
                chat_name=chat_name,
                content=startup_text,
                database_path=self.database_path,
                bot_key=self.bot_key,
                conversation_chat_id=conversation_chat_id,
                external_chat_id=external_chat_id,
                skip_record=True,
            )
        self._startup_broadcast_sent = True

    def _should_skip_startup_broadcast(self, conversation: dict[str, Any]) -> bool:
        chat_id = str(conversation.get("chat_id") or "").strip()
        external_chat_id = str(conversation.get("external_chat_id") or "").strip()
        conversation_kind = str(conversation.get("conversation_kind") or "").strip()

        if chat_id.startswith("precheck:") or external_chat_id.startswith("precheck:"):
            return True
        if conversation_kind == "me" and self._bound_chat_id:
            return external_chat_id != self._bound_chat_id
        return False

    async def _on_text_message(self, frame: dict[str, Any], *, trace_id_override: str = "") -> None:
        self._refresh_runtime_settings()
        trace_id = trace_id_override or str(uuid4())
        raw_context = extract_message_context(frame)
        message = extract_text_content(frame) or "<empty>"
        if message == "connect mycom":
            handled = await self._binding_manager.handle_bind_command(frame, raw_context, trace_id)
            if handled:
                return

        if is_command_attempt(message):
            if not self._binding_manager.is_personal_chat(raw_context):
                result = "群聊中不支持系统指令，请在私聊中使用。"
            else:
                keyword = _strip_at_prefix(message).lower()
                result = await dispatch_system_command(
                    keyword,
                    context={
                        "chat_id": self._conversation_context(raw_context).get("chat_id", ""),
                        "bot_key": self.bot_key,
                        "database_path": self.database_path,
                        "original_text": message,
                        "shutdown_callback": self._graceful_shutdown,
                        "bot_status": self._get_bot_status(),
                        "transfer_human_callback": self._send_transfer_human_notification,
                        "awaiting_exit_confirm": self._awaiting_exit_confirm,
                        "set_awaiting_exit_confirm": lambda v: setattr(self, '_awaiting_exit_confirm', v),
                    },
                    is_bound=self._binding_manager.is_bound_self_chat(raw_context),
                )
            if self._client is None:
                raise RuntimeError("WSClient not initialized")
            await self._client.reply_stream(
                frame,
                stream_id=build_stream_id(),
                content=result,
                finish=True,
            )
            return

        if is_no_prefix_command(message):
            keyword = _strip_at_prefix(message).lower()
            result = await dispatch_system_command(
                keyword,
                context={
                    "chat_id": self._conversation_context(raw_context).get("chat_id", ""),
                    "bot_key": self.bot_key,
                    "database_path": self.database_path,
                    "original_text": message,
                    "shutdown_callback": self._graceful_shutdown,
                    "bot_status": self._get_bot_status(),
                    "transfer_human_callback": self._send_transfer_human_notification,
                    "awaiting_exit_confirm": self._awaiting_exit_confirm,
                    "set_awaiting_exit_confirm": lambda v: setattr(self, '_awaiting_exit_confirm', v),
                },
                is_bound=self._binding_manager.is_bound_self_chat(raw_context),
            )
            if self._client is None:
                raise RuntimeError("WSClient not initialized")
            await self._client.reply_stream(
                frame,
                stream_id=build_stream_id(),
                content=result,
                finish=True,
            )
            return

        if self._binding_manager.is_binding_mode():
            await self._binding_manager.handle_binding_mode(frame, raw_context, is_text=True)
            return

        context = self._conversation_context(raw_context)
        self._record_user_message(context, message, "text", trace_id=trace_id)

        if not self._is_conversation_ai_mode(context):
            return

        acquired = False

        try:
            create_ai_work_item(
                self.database_path,
                trace_id=trace_id,
                chat_id=context.get("chat_id", "unknown"),
                chat_name=context.get("chat_name", context.get("chat_id", "unknown")),
                question=message,
                stage="接收消息",
            )
            acquired = await self._try_acquire_request_slot()
            if not acquired:
                self.logger.error(
                    "Request concurrency limit reached, returning busy reply",
                    extra={"trace_id": trace_id, "category": "task"},
                )
                update_ai_work_item(
                    self.database_path,
                    trace_id=trace_id,
                    status="busy",
                    stage="等待 Agent 并发槽",
                )
                await self._reply_busy_text(frame, context, trace_id=trace_id)
                return

            if is_chat_locked(self.database_path, chat_id=context.get("chat_id", "")):
                self.logger.warning(
                    "Chat is locked for compression, waiting for unlock",
                    extra={"trace_id": trace_id, "chat_id": context.get("chat_id", ""), "category": "task"},
                )
                update_ai_work_item(
                    self.database_path,
                    trace_id=trace_id,
                    status="running",
                    stage="等待上下文压缩",
                )
                await self._reply_busy_text(
                    frame,
                    context,
                    custom_notice="正在整理上下文，稍后自动回复",
                    trace_id=trace_id,
                )
                unlocked = await wait_for_chat_compress_unlock(
                    self.database_path,
                    chat_id=context.get("chat_id", ""),
                )
                if not unlocked:
                    self.logger.warning(
                        "Chat compress wait timed out, returning busy reply",
                        extra={"trace_id": trace_id, "chat_id": context.get("chat_id", ""), "category": "task"},
                    )
                    update_ai_work_item(
                        self.database_path,
                        trace_id=trace_id,
                        status="busy",
                        stage="上下文压缩等待超时",
                    )
                    return

            update_ai_work_item(
                self.database_path,
                trace_id=trace_id,
                status="running",
                stage="等待 Agent 并发槽",
            )
            await self._reply_agent_text(frame, message, context, trace_id)
        except Exception as exc:
            error_msg = f"Failed to process text message: {exc}"
            update_ai_work_item(
                self.database_path,
                trace_id=trace_id,
                status="failed",
                error=error_msg,
            )
            self.logger.exception(
                error_msg,
                extra={"trace_id": trace_id, "category": "task"},
            )
        finally:
            if acquired:
                await self._release_request_slot()

    async def _on_non_text_message(self, frame: dict[str, Any], *, trace_id_override: str = "") -> None:
        self._refresh_runtime_settings()
        trace_id = trace_id_override or str(uuid4())
        raw_context = extract_message_context(frame)
        context = self._conversation_context(raw_context)

        if self._binding_manager.is_binding_mode():
            await self._binding_manager.handle_binding_mode(frame, raw_context, is_text=False)
            return

        msgtype = str(frame.get("body", {}).get("msgtype", "unknown"))

        provider = self.settings.agent.providers.get(self.settings.agent.provider)
        if provider is None:
            self.logger.warning(
                "Agent provider not configured, skipping non-text message processing",
                extra={"trace_id": trace_id, "category": "ai"},
            )
            return
        caps = get_model_capabilities(
            provider.model, provider.type,
            user_override=provider.capabilities,
        )
        parsed_message = await self._media_handler.build_non_text_message_payload(frame, msgtype, caps, provider, trace_id=trace_id)
        user_input = parsed_message["user_input"]
        display_parts = await self._media_handler.materialize_display_parts(
            parsed_message["display_parts"],
            trace_id=trace_id,
        )
        parsed_message["display_parts"] = display_parts
        record_content = parsed_message["record_content"]

        media_parts = [p for p in display_parts if self._media_handler.is_forwardable_media_part(p)]
        media_types = [str(p.get("type") or "").strip().lower() for p in media_parts]
        has_media_part = bool(media_parts)

        message_metadata = {
            "trace_id": trace_id,
            "parts": display_parts,
            "raw_msg_type": msgtype,
            "source_kind": parsed_message["source_kind"],
            "agent_image_transport": parsed_message["agent_image_transport"],
            "agent_video_transport": parsed_message["agent_video_transport"],
            "unsupported_modalities": parsed_message["unsupported_modalities"],
            "contains_media": has_media_part,
            "media_types": media_types,
        }
        created_at = self._record_user_message(
            context,
            record_content,
            msgtype,
            trace_id=trace_id,
            metadata=message_metadata,
        )

        self._event_logger.emit(RuntimeEvent(
            trace_id=trace_id,
            source="message_parser",
            category=EventCategory.SYSTEM,
            message=f"非文本消息解析完成 raw_msg_type={msgtype} has_media={has_media_part} parts_count={len(display_parts)}",
            detail=f"parts_types={[p.get('type') for p in display_parts]}",
        ))

        oversized_parts = self._media_handler.size_limit_exceeded_parts(display_parts)
        if oversized_parts and str(context.get("chat_type") or "").strip() == "single":
            fallback_text = self.settings.agent.fallback_text
            self._event_logger.emit(RuntimeEvent(
                trace_id=trace_id,
                source="message_parser",
                category=EventCategory.MEDIA,
                message="私聊媒体超过大小限制，直接返回降级文本",
                detail=f"oversized_count={len(oversized_parts)}",
            ))
            await self._send_ai_reply_message(frame, context, fallback_text, trace_id=trace_id)
            self._record_bot_message(
                context,
                fallback_text,
                "system",
                sender_id="system",
                sender_name="系统",
                reply_source="system",
                trace_id=trace_id,
                metadata={
                    "media_size_limit": "fallback",
                    "oversized_count": len(oversized_parts),
                    "media_types": media_types,
                },
                mark_user_replied=True,
            )
            return

        # 保存是否需要延迟执行媒体转发
        need_delayed_forward = False
        if has_media_part:
            attachment_reply = bool(get_platform_settings().get("attachment_reply"))
            ai_mode = self._is_conversation_ai_mode(context)
            if attachment_reply and ai_mode:
                text_parts = [p for p in display_parts if p.get("type") == "text"]
                text_content = " ".join(str(p.get("text", "")).strip() for p in text_parts).strip()
                if text_content:
                    self._event_logger.emit(RuntimeEvent(
                        trace_id=trace_id,
                        source="media_forward",
                        category=EventCategory.MEDIA,
                        message="附件回复已开启，保留多模态输入走智能回复，同时异步执行转发",
                    ))
                    # 注意：不修改 user_input，保留原来的多模态内容（图片等）
                    record_content = text_content
                    # 标记需要延迟执行转发
                    need_delayed_forward = True
                else:
                    self._event_logger.emit(RuntimeEvent(
                        trace_id=trace_id,
                        source="media_forward",
                        category=EventCategory.MEDIA,
                        message="附件回复已开启，但无文本内容，走转发逻辑",
                    ))
                    await self._media_handler.handle_media_forward(frame, context, display_parts, created_at=created_at, trace_id=trace_id)
                    return
            else:
                self._event_logger.emit(RuntimeEvent(
                    trace_id=trace_id,
                    source="media_forward",
                    category=EventCategory.MEDIA,
                    message="媒体消息命中转发分支，不进 Agent",
                ))
                await self._media_handler.handle_media_forward(frame, context, display_parts, created_at=created_at, trace_id=trace_id)
                return

        if not self._is_conversation_ai_mode(context):
            return

        acquired = False

        try:
            create_ai_work_item(
                self.database_path,
                trace_id=trace_id,
                chat_id=context.get("chat_id", "unknown"),
                chat_name=context.get("chat_name", context.get("chat_id", "unknown")),
                question=record_content,
                stage="接收消息",
            )
            acquired = await self._try_acquire_request_slot()
            if not acquired:
                self.logger.error(
                    "Request concurrency limit reached, returning busy reply",
                    extra={"trace_id": trace_id, "category": "task"},
                )
                update_ai_work_item(
                    self.database_path,
                    trace_id=trace_id,
                    status="busy",
                    stage="等待 Agent 并发槽",
                )
                await self._reply_busy_text(frame, context, trace_id=trace_id)
                return

            if is_chat_locked(self.database_path, chat_id=context.get("chat_id", "")):
                self.logger.warning(
                    "Chat is locked for compression (non-text), waiting for unlock",
                    extra={"trace_id": trace_id, "chat_id": context.get("chat_id", ""), "category": "task"},
                )
                update_ai_work_item(
                    self.database_path,
                    trace_id=trace_id,
                    status="running",
                    stage="等待上下文压缩",
                )
                unlocked = await wait_for_chat_compress_unlock(
                    self.database_path,
                    chat_id=context.get("chat_id", ""),
                )
                if not unlocked:
                    self.logger.warning(
                        "Chat compress wait timed out (non-text), returning busy reply",
                        extra={"trace_id": trace_id, "chat_id": context.get("chat_id", ""), "category": "task"},
                    )
                    update_ai_work_item(
                        self.database_path,
                        trace_id=trace_id,
                        status="busy",
                        stage="上下文压缩等待超时",
                    )
                    await self._reply_busy_text(frame, context, trace_id=trace_id)
                    return

            update_ai_work_item(
                self.database_path,
                trace_id=trace_id,
                status="running",
                stage="等待 Agent 并发槽",
            )
            await self._reply_agent_text(
                frame,
                user_input,
                context,
                trace_id,
                need_delayed_forward=need_delayed_forward,
                display_parts=display_parts,
                created_at=created_at,
            )
        except Exception as exc:
            error_msg = f"Failed to process non-text message: {exc}"
            update_ai_work_item(
                self.database_path,
                trace_id=trace_id,
                status="failed",
                error=error_msg,
            )
            self.logger.exception(
                error_msg,
                extra={"trace_id": trace_id, "category": "task"},
            )
        finally:
            if acquired:
                await self._release_request_slot()


    @staticmethod
    def _format_local_message_time(created_at: str) -> str:
        raw = str(created_at or "").strip()
        if not raw:
            return "未知时间"
        try:
            dt = datetime.fromisoformat(raw)
        except ValueError:
            return raw
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=CST)
        return dt.astimezone(CST).strftime("%Y-%m-%d %H:%M:%S")


    async def _on_enter_chat(self, _frame: dict[str, Any]) -> None:
        self.bot_message_logger.info("[event] enter_chat")

    async def _reply_agent_text(
        self,
        frame: dict[str, Any],
        user_text: Any,
        context: dict[str, str],
        trace_id: str,
        *,
        need_delayed_forward: bool = False,
        display_parts: list[dict[str, Any]] | None = None,
        created_at: str = "",
    ) -> None:
        if self._client is None:
            raise RuntimeError("WSClient not initialized")

        orchestrator = StreamAnswerOrchestrator(
            database_path=self.database_path,
            trace_id=trace_id,
            agent_service=self.agent_service,
            bot_key=self.bot_key,
        )
        callbacks = StreamCallbacks(
            on_start=lambda: self._event_logger.ai_started(
                trace_id=trace_id,
                detail=self._task_detail(
                    chat_id=context.get("chat_id", ""),
                    chat_name=context.get("chat_name", ""),
                    question=user_text,
                    stage="构建上下文并调用 Agent（流式）",
                ),
            ),
            on_cancel=lambda: self._event_logger.ai_cancelled(
                trace_id=trace_id,
                detail=self._task_detail(
                    chat_id=context.get("chat_id", ""),
                    chat_name=context.get("chat_name", ""),
                    question=user_text,
                    stage="已截断",
                ),
            ),
        )

        result = await orchestrator.stream(
            user_text,
            chat_id=context.get("chat_id", ""),
            sender_id=str(context.get("sender_id") or ""),
            sender_name=str(context.get("sender_name") or ""),
            callbacks=callbacks,
        )

        if result.status == StreamStatus.CANCELLED:
            return

        if result.status == StreamStatus.FAILED:
            partial_answer = sanitize_agent_output(
                result.answer,
                self.settings.agent.fallback_text,
                max_chars=self.settings.agent.max_output_chars,
                truncation_notice=self.settings.agent.truncation_notice,
            )
            chat_id = context.get("chat_id", "")
            self._handle_conversation_send_failure(
                trace_id=trace_id,
                chat_id=chat_id,
                chat_name=context.get("chat_name", ""),
                error=result.error,
                reason="AI reply send failed",
            )
            self._event_logger.ai_failed(
                trace_id=trace_id,
                detail=self._task_detail(
                    chat_id=chat_id,
                    chat_name=context.get("chat_name", ""),
                    question=user_text,
                    answer=partial_answer,
                    stage="异常截断",
                    error=str(result.error),
                ),
            )

        if result.status != StreamStatus.COMPLETED:
            if need_delayed_forward and display_parts:
                self._event_logger.emit(RuntimeEvent(
                    trace_id=trace_id,
                    source="media_forward",
                    category=EventCategory.MEDIA,
                    message="AI 回复异常，执行延迟的媒体转发",
                ))
                try:
                    await self._media_handler.handle_media_forward(
                        frame,
                        context,
                        display_parts,
                        created_at=created_at,
                        trace_id=trace_id,
                        skip_reply=True,
                    )
                except Exception as e:
                    self.logger.exception(
                        "延迟媒体转发失败",
                        extra={"trace_id": trace_id, "error": str(e)},
                    )
            return

        full_answer = sanitize_agent_output(
            result.answer,
            self.settings.agent.fallback_text,
            max_chars=self.settings.agent.max_output_chars,
            truncation_notice=self.settings.agent.truncation_notice,
        )
        full_answer = self._with_ai_notice(full_answer)

        update_ai_work_item(
            self.database_path,
            trace_id=trace_id,
            status="running",
            stage="发送企微回复",
        )
        try:
            await self._send_ai_reply_message(frame, context, full_answer, trace_id=trace_id)
        except Exception as send_exc:
            self.logger.error(
                "AI reply send failed after retries, sending fallback: %s",
                send_exc,
                extra={"trace_id": trace_id, "category": "network"},
            )
            try:
                await self._client.send_message(
                    str(context.get("chat_id") or context.get("external_chat_id") or "").strip(),
                    {
                        "msgtype": "text",
                        "text": {"content": self.settings.agent.fallback_text},
                    },
                )
            except Exception as fallback_exc:
                self.logger.error(
                    "Fallback send also failed: %s",
                    fallback_exc,
                    extra={"trace_id": trace_id, "category": "network"},
                )
            self._handle_conversation_send_failure(
                trace_id=trace_id,
                chat_id=context.get("chat_id", ""),
                chat_name=context.get("chat_name", ""),
                error=str(send_exc),
                reason="AI reply send failed after retries",
            )
            self._event_logger.ai_failed(
                trace_id=trace_id,
                detail=self._task_detail(
                    chat_id=context.get("chat_id", ""),
                    chat_name=context.get("chat_name", ""),
                    question=user_text,
                    answer=full_answer,
                    stage="发送失败",
                    error=str(send_exc),
                ),
            )
            return

        self._record_bot_message(
            context,
            full_answer,
            "agent",
            reply_source="ai",
            trace_id=trace_id,
        )
        update_ai_work_item(
            self.database_path,
            trace_id=trace_id,
            status="completed",
            answer=full_answer,
            stage="完成",
        )
        self._event_logger.ai_completed(
            trace_id=trace_id,
            detail=self._task_detail(
                chat_id=context.get("chat_id", ""),
                chat_name=context.get("chat_name", ""),
                question=user_text,
                answer=full_answer,
                stage="完成",
            ),
        )
        self._log_token_usage(trace_id=trace_id, message="AI task token usage")
        compress_result = await self.agent_service.compress_context_if_needed(
            context.get("chat_id", ""),
            sender_id=str(context.get("sender_id") or ""),
            sender_name=str(context.get("sender_name") or ""),
            bot_key=self.bot_key,
            trace_id=trace_id,
        )
        if compress_result.get("triggered") and compress_result.get("compressed"):
            try:
                compress_notice = "（上下文已压缩，回复质量已优化）"
                await self._client.reply_stream(
                    frame,
                    stream_id=build_stream_id(),
                    content=compress_notice,
                    finish=True,
                )
                self._record_bot_message(
                    context,
                    compress_notice,
                    "system",
                    reply_source="system",
                    trace_id=trace_id,
                )
            except Exception:
                self.logger.exception(
                    "发送压缩通知失败",
                    extra={"trace_id": trace_id, "category": "ai"},
                )

        # 现在执行延迟的媒体转发
        if need_delayed_forward and display_parts:
            self._event_logger.emit(RuntimeEvent(
                trace_id=trace_id,
                source="media_forward",
                category=EventCategory.MEDIA,
                message="开始执行延迟的媒体转发",
            ))
            try:
                await self._media_handler.handle_media_forward(
                    frame,
                    context,
                    display_parts,
                    created_at=created_at,
                    trace_id=trace_id,
                    skip_reply=True,
                )
            except Exception as e:
                self.logger.exception(
                    "延迟媒体转发失败",
                    extra={"trace_id": trace_id, "error": str(e)},
                )

    async def _send_ai_reply_message(
        self,
        frame: dict[str, Any],
        context: dict[str, str],
        content: str,
        *,
        trace_id: str = "",
    ) -> None:
        if self._client is None:
            raise RuntimeError("WSClient not initialized")

        text = content.strip()
        if not text:
            raise ValueError("AI reply content is empty")

        feedback_id = trace_id or build_stream_id()
        last_reply_exc: Exception | None = None
        for attempt in range(1, 4):
            try:
                await self._client.reply_stream(
                    frame,
                    stream_id=build_stream_id(),
                    content=text,
                    finish=True,
                    feedback={"id": feedback_id},
                )
                if attempt > 1:
                    self.logger.info(
                        "Passive reply succeeded on attempt %d/3",
                        attempt,
                        extra={"trace_id": trace_id, "category": "network"},
                    )
                return
            except Exception as reply_exc:
                last_reply_exc = reply_exc
                is_timeout = "ack timeout" in str(reply_exc).lower() or "timeout" in str(reply_exc).lower()
                if attempt < 3:
                    delay = 2.0 * attempt
                    self.logger.warning(
                        "Passive reply failed (attempt %d/3), retrying in %.1fs: %s",
                        attempt,
                        delay,
                        reply_exc,
                        extra={
                            "trace_id": trace_id,
                            "category": "network",
                            "attempt": attempt,
                            "is_timeout": is_timeout,
                        },
                    )
                    await asyncio.sleep(delay)
                else:
                    self.logger.warning(
                        "Passive reply failed after 3 attempts, falling back to active send: %s",
                        reply_exc,
                        extra={
                            "trace_id": trace_id,
                            "category": "network",
                            "attempt": attempt,
                            "is_timeout": is_timeout,
                        },
                    )

        external_chat_id = str(context.get("external_chat_id") or "").strip()
        conversation_chat_id = str(context.get("chat_id") or external_chat_id).strip()
        me_chat_id = make_conversation_key(self.bot_key, self._bound_chat_id, kind="me")
        is_me_chat = conversation_chat_id == me_chat_id and bool(self._bound_chat_id)
        actual_send_chat_id = self._bound_chat_id if is_me_chat else external_chat_id
        if not actual_send_chat_id:
            raise ValueError("AI reply target chat_id is missing")

        await self._send_message_with_retry(
            actual_send_chat_id,
            {
                "msgtype": "markdown",
                "markdown": {"content": text},
            },
            trace_id=trace_id,
        )

    async def _send_message_with_retry(
        self,
        chat_id: str,
        message: dict[str, Any],
        *,
        trace_id: str = "",
        max_retries: int = 3,
        base_delay: float = 2.0,
    ) -> None:
        last_exc: Exception | None = None
        for attempt in range(1, max_retries + 1):
            try:
                await self._client.send_message(chat_id, message)
                if attempt > 1:
                    self.logger.info(
                        "Message sent successfully on attempt %d/%d",
                        attempt,
                        max_retries,
                        extra={"trace_id": trace_id, "category": "network"},
                    )
                return
            except Exception as exc:
                last_exc = exc
                is_timeout = "ack timeout" in str(exc).lower() or "timeout" in str(exc).lower()
                if attempt < max_retries:
                    delay = base_delay * attempt
                    self.logger.warning(
                        "Send message failed (attempt %d/%d), retrying in %.1fs: %s",
                        attempt,
                        max_retries,
                        delay,
                        exc,
                        extra={
                            "trace_id": trace_id,
                            "category": "network",
                            "attempt": attempt,
                            "is_timeout": is_timeout,
                        },
                    )
                    await asyncio.sleep(delay)
                else:
                    self.logger.error(
                        "Send message failed after %d attempts: %s",
                        max_retries,
                        exc,
                        extra={
                            "trace_id": trace_id,
                            "category": "network",
                            "attempt": attempt,
                            "is_timeout": is_timeout,
                        },
                    )
        if last_exc is not None:
            raise last_exc

    async def _reply_busy_text(
        self,
        frame: dict[str, Any],
        context: dict[str, str],
        *,
        custom_notice: str = "",
        trace_id: str = "",
    ) -> None:
        if self._client is None:
            raise RuntimeError("WSClient not initialized")
        notice = custom_notice or self.settings.runtime.busy_reply_text
        await self._client.reply_stream(
            frame,
            stream_id=build_stream_id(),
            content=notice,
            finish=True,
        )
        self._record_bot_message(
            context,
            notice,
            "busy",
            reply_source="system",
            trace_id=trace_id,
        )

    def _task_detail(
        self,
        *,
        chat_id: str,
        chat_name: str,
        question: str = "",
        answer: str = "",
        stage: str = "",
        error: str = "",
    ) -> str:
        parts = [
            f"bot_key={self.bot_key}",
            f"chat_id={chat_id or '<empty>'}",
            f"chat_name={chat_name or '<empty>'}",
        ]
        if stage:
            parts.append(f"stage={stage}")
        if question:
            parts.append(f"question={_one_line(question[:500])}")
        if answer:
            parts.append(f"answer={_one_line(answer[:1200])}")
        if error:
            parts.append(f"error={_one_line(error[:1200])}")
        return "\n".join(parts)

    def _handle_conversation_send_failure(
        self,
        *,
        trace_id: str,
        chat_id: str,
        chat_name: str,
        error: Exception,
        reason: str,
    ) -> None:
        if chat_id:
            set_conversation_send_error(
                chat_id=chat_id,
                error=str(error),
                database_path=self.database_path,
            )
        self._event_logger.network_event(
            trace_id=trace_id,
            message=reason,
            detail=self._task_detail(
                chat_id=chat_id,
                chat_name=chat_name,
                error=str(error),
            ),
        )


    async def _try_acquire_request_slot(self) -> bool:
        async with self._request_lock:
            if self._active_requests >= self.settings.runtime.max_concurrent_requests:
                return False

            self._active_requests += 1
            return True

    async def _release_request_slot(self) -> None:
        async with self._request_lock:
            if self._active_requests > 0:
                self._active_requests -= 1

    def _record_user_message(
        self,
        context: dict[str, str],
        content: str,
        msg_type: str,
        *,
        trace_id: str = "",
        metadata: dict[str, Any] | None = None,
    ) -> str:
        self.bot_message_logger.info(
            "[user] chat=%s sender=%s(%s) %s",
            context.get("chat_id", "unknown"),
            context.get("sender_name", "未知用户"),
            context.get("sender_id", "unknown"),
            _one_line(content),
        )
        return self._append_chat_message(
            direction="user",
            context=context,
            sender_id=context.get("sender_id", "unknown"),
            sender_name=context.get("sender_name", "未知用户"),
            content=content,
            msg_type=msg_type,
            reply_source="user",
            trace_id=trace_id,
            metadata=metadata,
        )

    def _record_bot_message(
        self,
        context: dict[str, str],
        content: str,
        msg_type: str,
        *,
        sender_id: str = "bot",
        sender_name: str = "AI Bot",
        reply_source: str = "ai",
        trace_id: str = "",
        metadata: dict[str, Any] | None = None,
        mark_user_replied: bool | None = None,
    ) -> None:
        self.bot_message_logger.info(
            "[bot] chat=%s sender=%s %s",
            context.get("chat_id", "unknown"),
            sender_name,
            _one_line(content),
        )
        # 默认只有 agent、manual 类型消息才更新用户消息回复状态
        if mark_user_replied is None:
            mark_user_replied = msg_type in ("agent", "manual")
        target_sender_id = str(context.get("context_sender_id") or context.get("sender_id") or "").strip()
        target_sender_name = str(context.get("context_sender_name") or context.get("sender_name") or "").strip()
        message_metadata = dict(metadata or {})
        if target_sender_id:
            message_metadata.setdefault("context_sender_id", target_sender_id)
        if target_sender_name:
            message_metadata.setdefault("context_sender_name", target_sender_name)
        self._append_chat_message(
            direction="bot",
            context=context,
            sender_id=sender_id,
            sender_name=sender_name,
            content=content,
            msg_type=msg_type,
            reply_source=reply_source,
            trace_id=trace_id,
            metadata=message_metadata,
            mark_user_replied=mark_user_replied,
        )

    def _append_chat_message(
        self,
        *,
        direction: str,
        context: dict[str, str],
        sender_id: str,
        sender_name: str,
        content: str,
        msg_type: str,
        reply_source: str,
        trace_id: str,
        metadata: dict[str, Any] | None,
        mark_user_replied: bool = True,
    ) -> str:
        try:
            merged_metadata = dict(metadata or {})
            if trace_id and "trace_id" not in merged_metadata:
                merged_metadata["trace_id"] = trace_id
            # 使用 chat_name 作为 potential display_name
            display_name = context.get("chat_name")
            msg = append_chat_message(
                direction=direction,
                chat_id=context.get("chat_id", "unknown"),
                chat_name=context.get("chat_name", context.get("chat_id", "unknown")),
                sender_id=sender_id,
                sender_name=sender_name,
                content=content,
                msg_type=msg_type,
                database_path=self.database_path,
                reply_source=reply_source,
                bot_key=context.get("bot_key", self.bot_key),
                external_chat_id=context.get("external_chat_id", context.get("chat_id", "")),
                conversation_kind=context.get("conversation_kind", "external"),
                chat_type=context.get("chat_type", "unknown"),
                metadata=merged_metadata,
                mark_user_replied=mark_user_replied,
                context_sender_id=str(context.get("context_sender_id") or context.get("sender_id") or "").strip(),
                display_name=display_name,
            )
            return str(msg.created_at) if msg else ""
        except Exception:
            self.logger.exception("Failed to append chat message.", extra={"category": "data"})
            return ""

    def _refresh_runtime_settings(self) -> None:
        try:
            next_settings = get_bot_runtime_settings(
                self.database_path,
                bot_key=self.bot_key,
            )
        except Exception:
            self.logger.exception("Failed to reload runtime config.", extra={"category": "system"})
            return

        if next_settings.agent.providers != self.agent_service.settings.agent.providers:
            self.agent_service.settings = next_settings
            self.agent_service.invalidate_cache()
            self.logger.info("Agent settings changed, cache invalidated", extra={"category": "system"})
        else:
            self.agent_service.settings = next_settings

        self.settings = next_settings
        self._binding_manager.refresh_bound_state()

    def _conversation_context(self, raw_context: dict[str, str]) -> dict[str, str]:
        if raw_context.get("bot_key"):
            return raw_context

        external_chat_id = raw_context.get("chat_id", "unknown")
        kind = raw_context.get("conversation_kind", "external") or "external"
        chat_type = self._binding_manager.chat_type_for_context(raw_context)
        chat_name = raw_context.get("chat_name", external_chat_id)
        sender_name = raw_context.get("sender_name", "未知用户")
        if self._binding_manager.is_bound_self_chat(raw_context):
            kind = "me"
            chat_type = "single"
            chat_name = self._bound_chat_name
            # 注意：这里不再将 sender_name 强制设为 "我"
            # 因为 is_bound_self_chat 会匹配所有来自绑定用户的单聊消息
            # 包括普通用户发送给 Bot 的消息，这些消息的 sender 应该是用户自己
            # "我" 的标识只在会话层面（conversation_kind="me"）体现
        conversation_id = make_conversation_key(
            self.bot_key,
            external_chat_id,
            kind=kind,
        )
        context = dict(raw_context)
        context["external_chat_id"] = external_chat_id
        context["chat_id"] = conversation_id
        context["chat_name"] = chat_name
        context["bot_key"] = self.bot_key
        context["conversation_kind"] = kind
        context["chat_type"] = chat_type
        context["sender_name"] = sender_name
        return context


    def _is_conversation_ai_mode(self, context: dict[str, str]) -> bool:
        if not self.settings.agent.enabled:
            return False
        chat_id = context.get("chat_id", "")
        if not chat_id or chat_id == "unknown":
            return False
        try:
            conversation = get_conversation(chat_id=chat_id, database_path=self.database_path)
            if conversation:
                return str(conversation.get("reply_mode", "manual")) == "ai"
        except Exception:
            self.logger.exception(
                "Database error reading reply_mode for chat %s — degrading to manual mode",
                chat_id,
                extra={"category": "data"},
            )
        return False

    def _with_ai_notice(self, answer: str) -> str:
        text = answer.strip() or self.settings.agent.fallback_text
        notice = self.settings.agent.reply_notice
        if not notice:
            return text
        if notice in text:
            return text
        return f"{text}\n\n({notice})"

    def _store_frame(self, trace_id: str, frame: dict[str, Any], *, chat_id: str = "") -> None:
        self._frame_store.store(trace_id, frame, chat_id=chat_id)


    def _frame_req_id(self, frame: dict[str, Any] | None) -> str:
        if not isinstance(frame, dict):
            return ""
        headers = frame.get("headers")
        if not isinstance(headers, dict):
            return ""
        return str(headers.get("req_id") or "").strip()

    def _log_token_usage(self, *, trace_id: str, message: str) -> None:
        usage = get_latest_token_usage(self.database_path, trace_id=trace_id)
        if not usage:
            return
        self._event_logger.token_usage(
            trace_id=trace_id,
            message=message,
            detail=(
                f"call_type={usage.get('call_type', '')}\n"
                f"provider_key={usage.get('provider_key', '')}\n"
                f"provider_type={usage.get('provider_type', '')}\n"
                f"model={usage.get('model', '')}\n"
                f"input_tokens={usage.get('input_tokens', 0)}\n"
                f"output_tokens={usage.get('output_tokens', 0)}\n"
                f"total_tokens={usage.get('total_tokens', 0)}"
            ),
        )

    async def _graceful_shutdown(self) -> None:
        from app.routers.bots import _send_shutdown_text_if_needed

        if self._client is not None:
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(
                None,
                lambda: _send_shutdown_text_if_needed(
                    bot_key=self.bot_key,
                    database_path=self.database_path,
                ),
            )
        self._keepalive.set()

    async def _send_transfer_human_notification(self, chat_id: str) -> str:
        from app.chat_store import get_conversation

        conversation = get_conversation(chat_id=chat_id, database_path=self.database_path)
        chat_type = str((conversation or {}).get("chat_type") or "unknown")
        display_name = str((conversation or {}).get("display_name") or (conversation or {}).get("chat_name") or chat_id)

        last_msg = self._get_last_user_message(chat_id)
        sender_name = last_msg.get("sender_name", "未知用户")
        sender_id = last_msg.get("sender_id", "")
        content = last_msg.get("content", "")
        msg_time = last_msg.get("created_at", "")

        # 优先使用用户映射表中的显示名称
        if sender_id:
            user_profile = get_user_display_name(self.database_path, sender_id)
            if user_profile and user_profile.get("display_name"):
                sender_name = user_profile["display_name"]

        if msg_time:
            try:
                from datetime import datetime as _dt
                dt = _dt.fromisoformat(msg_time)
                formatted_time = dt.astimezone(CST).strftime("%Y-%m-%d %H:%M:%S")
            except (ValueError, OSError):
                formatted_time = msg_time
        else:
            from app.utils import utc_now
            formatted_time = utc_now()

        if chat_type in ("group", "room"):
            source_label = f"群聊[{display_name}]用户[{sender_name}]"
        else:
            source_label = f"用户[{display_name}]"

        notification = f"{source_label} 于 {formatted_time} 发送了 [{content}] 请马上处理"

        if self._bound_chat_id and self._client is not None:
            me_conversation_id = make_conversation_key(self.bot_key, self._bound_chat_id, kind="me")
            enqueue_manual_reply(
                chat_id=self._bound_chat_id,
                chat_name=self._bound_chat_name,
                content=notification,
                database_path=self.database_path,
                bot_key=self.bot_key,
                conversation_chat_id=me_conversation_id,
                external_chat_id=self._bound_chat_id,
                skip_record=True,
            )
            return "已通知管理员，请稍候。"
        return "暂无人管理员在线，请稍后再试。"

    def _get_last_user_message(self, chat_id: str) -> dict[str, str]:
        initialize_database(self.database_path)
        with connect_database(self.database_path) as conn:
            row = conn.execute(
                """
                SELECT content, sender_name, sender_id, created_at
                FROM chat_messages
                WHERE chat_id = ?
                  AND direction = 'user'
                  AND msg_type NOT IN ('system', 'busy', 'context_summary')
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (chat_id,),
            ).fetchone()
        if not row:
            return {}
        return {
            "content": str(row["content"] or ""),
            "sender_name": str(row["sender_name"] or ""),
            "sender_id": str(row["sender_id"] or ""),
            "created_at": str(row["created_at"] or ""),
        }

    def _get_bot_status(self) -> dict[str, Any]:
        started_at = ""
        pid_file = self.project_root / "data" / f"bot-{self.bot_key}.pid"
        if pid_file.exists():
            try:
                started_at = str(pid_file.stat().st_ctime)
            except OSError:
                pass
        active_conversations = len(
            list_active_bot_conversations(bot_key=self.bot_key, database_path=self.database_path)
        )
        return {
            "bot_name": self.settings.wecom_bot.name,
            "running": True,
            "bound": bool(self._bound_user_id),
            "bound_chat_name": self._bound_chat_name,
            "started_at": started_at,
            "active_conversations": active_conversations,
        }

    async def _watch_parent_process(self) -> None:
        if self.parent_pid is None:
            return

        while not self._keepalive.is_set():
            if not is_process_running(self.parent_pid):
                self._keepalive.set()
                return
            await asyncio.sleep(2)


def _one_line(content: str) -> str:
    return str(content).replace("\r", " ").replace("\n", "\\n")


async def run_long_connection(
    settings: Settings,
    parent_pid: int | None = None,
    project_root: Path | None = None,
    bot_key: str = "",
) -> None:
    """启动企微机器人长连接模式的入口函数。

    初始化运行时内存，创建 AgentLongConnectionBot 实例并启动事件循环。
    该函数通常由进程管理器调用，每个机器人实例对应一个独立进程。

    Args:
        settings: 机器人运行时配置。
        parent_pid: 父进程 ID，用于进程监控；为 None 时不启用监控。
        project_root: 项目根目录路径。
        bot_key: 机器人的唯一标识键。
    """
    from agent_runtime.skills_integration import init_memory
    await init_memory(project_root=project_root)
    bot = AgentLongConnectionBot(
        settings,
        parent_pid=parent_pid,
        project_root=project_root,
        bot_key=bot_key,
    )
    await bot.run()
