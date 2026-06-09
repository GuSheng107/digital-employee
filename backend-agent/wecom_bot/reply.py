from __future__ import annotations

"""消息上下文提取与回复构建工具模块。

提供从企微 WebSocket 帧中提取消息上下文（发送者、会话、消息ID等）、
提取文本内容以及构建流式回复标识等工具函数，供长连接机器人及
各处理器模块使用。
"""

from dataclasses import dataclass, asdict
from typing import Any


@dataclass(slots=True)
class MessageContext:
    """消息上下文数据类，封装从企微帧中提取的核心上下文字段。"""
    chat_id: str
    chat_name: str
    sender_id: str
    sender_name: str
    msg_type: str
    message_id: str


def build_stream_id() -> str:
    """生成唯一的流式回复标识符，用于企微被动回复的 stream_id 参数。"""
    from uuid import uuid4

    return uuid4().hex


def extract_text_content(frame: dict[str, Any]) -> str:
    """从企微帧中提取文本消息内容。

    Args:
        frame: 企微 WebSocket 帧字典。

    Returns:
        提取到的文本内容字符串，若无法提取则返回空字符串。
    """
    body = frame.get("body", {})
    text = body.get("text", {})
    content = text.get("content")
    if isinstance(content, str):
        return content.strip()
    return ""


def extract_message_context(frame: dict[str, Any]) -> dict[str, str]:
    """从企微帧中提取完整的消息上下文信息。

    解析帧中的 body 和 headers，提取 chat_id、sender_id、sender_name、
    chat_name、msg_type、message_id 等关键字段。对于缺失的字段会进行
    合理的默认值填充（如 sender_id 默认为 "unknown"）。

    Args:
        frame: 企微 WebSocket 帧字典。

    Returns:
        包含所有上下文字段的字典，字段名与 MessageContext 数据类一致。
    """
    body = frame.get("body", {})
    headers = frame.get("headers", {})

    msg_type = _string_value(body.get("msgtype")) or "unknown"
    sender_id_keys = {
        "from",
        "userid",
        "user_id",
        "user_openid",
        "from_userid",
        "from_user_id",
        "from_user",
        "sender_userid",
        "sender_user_id",
        "sender_id",
        "open_userid",
        "open_user_id",
        "open_kfid",
        "external_userid",
        "external_user_id",
    }
    sender_name_keys = {
        "username",
        "user_name",
        "sender_name",
        "sender_display_name",
        "sender_nickname",
        "real_name",
        "realname",
        "displayname",
        "nickname",
        "nick_name",
        "display_name",
        "from_name",
        "from_user_name",
        "from_display_name",
        "external_user_name",
        "member_name",
        "operator_name",
        "name",
    }

    sender_id = _find_string_in_named_objects(
        body,
        {"sender", "from", "user", "member", "source", "operator", "from_user"},
        sender_id_keys,
    ) or _find_string(
        body,
        sender_id_keys,
    )
    sender_name = _find_string_in_named_objects(
        body,
        {"sender", "from", "user", "member", "source", "operator", "from_user"},
        sender_name_keys,
    ) or _find_string(
        body,
        sender_name_keys,
    )
    chat_id = _find_string(
        body,
        {
            "chatid",
            "chat_id",
            "conversation_id",
            "roomid",
            "room_id",
            "group_chatid",
            "group_chat_id",
        },
    )
    chat_name = _find_string_in_named_objects(
        body,
        {"chat", "conversation", "room", "group"},
        {"display_name", "chat_name", "name", "title", "nickname"}
    ) or _find_string(
        body,
        {
            "display_name",
            "chat_name",
            "conversation_name",
            "room_name",
            "group_name",
            "group_chat_name",
            "name",
            "title",
        },
    )
    message_id = _find_string(
        body,
        {
            "msgid",
            "msg_id",
            "message_id",
            "messageid",
        },
    )

    req_id = _string_value(headers.get("req_id"))
    if not sender_id:
        sender_id = "unknown"
    if not sender_name or sender_name in {sender_id, chat_id}:
        sender_name = _friendly_user_label(sender_id)
    if not chat_id:
        # Active single-chat sends use the user's userid as chatid.
        chat_id = sender_id if sender_id != "unknown" else (req_id or "unknown")
    if not chat_name:
        if chat_id and sender_id and chat_id != sender_id:
            # Group callbacks may omit a room name; keep the room id instead
            # of falling back to the sender label.
            chat_name = chat_id
        else:
            chat_name = sender_name if sender_name != "未知用户" else chat_id
    if not message_id:
        message_id = req_id or ""

    return asdict(
        MessageContext(
            chat_id=chat_id,
            chat_name=chat_name,
            sender_id=sender_id,
            sender_name=sender_name,
            msg_type=msg_type,
            message_id=message_id,
        )
    )


def _find_string(data: Any, keys: set[str], depth: int = 0) -> str:
    if depth > 10:
        return ""

    if isinstance(data, dict):
        normalized = {_normalize_key(key): key for key in data}
        for key in keys:
            original_key = normalized.get(_normalize_key(key))
            if original_key is None:
                continue
            value = _string_value(data.get(original_key))
            if value:
                return value

        for value in data.values():
            found = _find_string(value, keys, depth + 1)
            if found:
                return found

    if isinstance(data, list):
        for item in data:
            found = _find_string(item, keys, depth + 1)
            if found:
                return found

    return ""


def _find_string_in_named_objects(
    data: Any,
    object_keys: set[str],
    value_keys: set[str],
    depth: int = 0,
) -> str:
    if depth > 5:
        return ""

    if isinstance(data, dict):
        normalized = {_normalize_key(key): key for key in data}
        for object_key in object_keys:
            original_key = normalized.get(_normalize_key(object_key))
            if original_key is None:
                continue
            found = _find_string(data.get(original_key), value_keys, depth + 1)
            if found:
                return found

        for value in data.values():
            found = _find_string_in_named_objects(value, object_keys, value_keys, depth + 1)
            if found:
                return found

    if isinstance(data, list):
        for item in data:
            found = _find_string_in_named_objects(item, object_keys, value_keys, depth + 1)
            if found:
                return found

    return ""


def _string_value(value: Any) -> str:
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, int):
        return str(value)
    return ""


def _normalize_key(value: Any) -> str:
    text = str(value or "").strip().lower()
    return "".join(char for char in text if char.isalnum())


def _friendly_user_label(user_id: str) -> str:
    if not user_id or user_id == "unknown":
        return "未知用户"

    if len(user_id) <= 8:
        return f"企微用户 {user_id}"

    return f"企微用户 {user_id[:8]}"
