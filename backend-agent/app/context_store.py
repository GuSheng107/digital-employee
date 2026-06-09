from __future__ import annotations

"""对话上下文管理模块。

管理会话上下文的构建、压缩和摘要维护，包括上下文提示词构建、
智能截断、上下文使用量统计、压缩转录文本生成等功能。
"""

import json
from pathlib import Path
from typing import Any

from app.config_loader import Settings
from app.db.core import connect_database, initialize_database
from app.db.user_store import list_user_display_names
from app.utils import utc_now
from app.yaml_config import get_yaml_config


def _item_value(item: Any, key: str, default: Any = "") -> Any:
    if isinstance(item, dict):
        return item.get(key, default)
    keys = getattr(item, "keys", None)
    if callable(keys) and key in keys():
        return item[key]
    return default


def _clean_sender_id(sender_id: str | None) -> str:
    return str(sender_id or "").strip()


def _message_metadata(item: dict[str, Any]) -> dict[str, Any]:
    metadata_json = str(item.get("metadata_json") or "").strip()
    if not metadata_json:
        return {}
    try:
        data = json.loads(metadata_json)
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _message_context_sender_id(item: dict[str, Any]) -> str:
    metadata = _message_metadata(item)
    for key in ("context_sender_id", "target_sender_id"):
        value = _clean_sender_id(metadata.get(key))
        if value:
            return value
    return ""


def _metadata_sender_like_patterns(sender_id: str) -> tuple[str, str]:
    encoded_sender_id = json.dumps(_clean_sender_id(sender_id), ensure_ascii=False)
    return (
        f'%"context_sender_id": {encoded_sender_id}%',
        f'%"target_sender_id": {encoded_sender_id}%',
    )


def _filter_context_rows_for_sender(rows: list[Any], sender_id: str) -> list[dict[str, Any]]:
    target_sender_id = _clean_sender_id(sender_id)
    items = [dict(row) for row in rows]
    if not target_sender_id:
        return items

    filtered: list[dict[str, Any]] = []
    current_user_sender_id = ""
    for item in items:
        direction = str(item.get("direction") or "").strip()
        if direction == "user":
            current_user_sender_id = _clean_sender_id(item.get("sender_id"))
            if current_user_sender_id == target_sender_id:
                filtered.append(item)
            continue

        owner_sender_id = _message_context_sender_id(item) or current_user_sender_id
        if owner_sender_id == target_sender_id:
            filtered.append(item)

    return filtered


def resolve_context_sender(
    *,
    database_path: Path,
    chat_id: str,
    sender_id: str = "",
    sender_name: str = "",
) -> dict[str, str]:
    clean_sender_id = _clean_sender_id(sender_id)
    clean_sender_name = str(sender_name or "").strip()
    if clean_sender_id:
        return {"sender_id": clean_sender_id, "sender_name": clean_sender_name}
    if not chat_id or chat_id == "unknown":
        return {"sender_id": "", "sender_name": clean_sender_name}

    initialize_database(database_path)
    from app.chat_store import get_conversation, get_last_unreplied_user_message

    last_unreplied = get_last_unreplied_user_message(chat_id=chat_id, database_path=database_path)
    last_sender_id = _clean_sender_id(last_unreplied.get("sender_id"))
    if last_sender_id:
        return {
            "sender_id": last_sender_id,
            "sender_name": str(last_unreplied.get("sender_name") or "").strip(),
        }

    with connect_database(database_path) as conn:
        latest_user = conn.execute(
            """
            SELECT sender_id, sender_name
            FROM chat_messages
            WHERE chat_id = ?
              AND direction = 'user'
              AND msg_type NOT IN ('system', 'busy', 'context_summary')
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (chat_id,),
        ).fetchone()
    if latest_user:
        latest_sender_id = _clean_sender_id(latest_user["sender_id"])
        if latest_sender_id:
            return {
                "sender_id": latest_sender_id,
                "sender_name": str(latest_user["sender_name"] or "").strip(),
            }

    conversation = get_conversation(chat_id=chat_id, database_path=database_path)
    if conversation:
        conversation_sender_id = _clean_sender_id(conversation.get("sender_id"))
        if conversation_sender_id:
            return {
                "sender_id": conversation_sender_id,
                "sender_name": str(conversation.get("sender_name") or "").strip(),
            }

    return {"sender_id": "", "sender_name": clean_sender_name}


def smart_truncate(text: str, max_chars: int, suffix: str = " [内容已截断]") -> str:
    """智能截断文本，优先在换行符、句号、标点等自然断点处截断。

    按优先级依次尝试在换行符、中文句号、感叹号/问号、空格处截断，
    如果均未找到合适的断点，则在最大字符数处硬截断。

    Args:
        text: 待截断的文本。
        max_chars: 最大字符数限制。
        suffix: 截断后追加的后缀文本。

    Returns:
        截断后的文本。
    """
    if len(text) <= max_chars:
        return text
    
    available_chars = max_chars - len(suffix)
    if available_chars <= 0:
        return text[:max_chars]
    
    candidate_pos = text.rfind('\n', 0, available_chars)
    if candidate_pos > available_chars * 0.7:
        return text[:candidate_pos].rstrip() + suffix
    
    candidate_pos = text.rfind('。', 0, available_chars)
    if candidate_pos > available_chars * 0.7:
        return text[:candidate_pos+1].rstrip() + suffix
    
    for punc in ['！', '？', '!', '?']:
        candidate_pos = text.rfind(punc, 0, available_chars)
        if candidate_pos > available_chars * 0.7:
            return text[:candidate_pos+1].rstrip() + suffix
    
    candidate_pos = text.rfind(' ', 0, available_chars)
    if candidate_pos > available_chars * 0.5:
        return text[:candidate_pos].rstrip() + suffix
    
    return text[:available_chars].rstrip() + suffix


def build_context_prompt(
    *,
    database_path: Path,
    chat_id: str,
    sender_id: str = "",
    sender_name: str = "",
    settings: Settings | None = None,
) -> str:
    """构建上下文提示词，包含会话摘要等最高优先级上下文信息。

    从数据库中读取会话的上下文摘要，拼接为结构化的提示词文本，
    供 Agent 回复时作为最高优先级参考。

    Args:
        database_path: 数据库文件路径。
        chat_id: 会话 ID。
        settings: 可选的配置对象，用于获取摘要字符限制。

    Returns:
        拼接后的上下文提示词字符串。
    """
    if not chat_id or chat_id == "unknown":
        return ""

    initialize_database(database_path)
    context_sender = resolve_context_sender(
        database_path=database_path,
        chat_id=chat_id,
        sender_id=sender_id,
        sender_name=sender_name,
    )
    context_sender_id = context_sender["sender_id"]
    summary = get_context_summary(
        database_path=database_path,
        chat_id=chat_id,
        sender_id=context_sender_id,
    )

    parts: list[str] = []
    if summary:
        summary_text = str(summary["summary"] or "").strip()
        summary_limit = _summary_in_prompt_max_chars(settings)
        if summary_limit > 0 and len(summary_text) > summary_limit:
            summary_text = smart_truncate(summary_text, summary_limit, " [摘要部分截断]")
        parts.append(
            "\n".join(
                [
                    "【最高优先级上下文摘要】",
                    "以下摘要只覆盖当前发问用户的历史对话，不包含同群其他成员的上下文。",
                    summary_text,
                    "【摘要说明】以上摘要覆盖较早对话，回答时优先保持其中的事实、偏好和约束。",
                ]
            )
        )

    return "\n\n".join(parts).strip()


def build_recent_messages_prompt(
    *,
    database_path: Path,
    chat_id: str,
    sender_id: str = "",
    sender_name: str = "",
    settings: Settings | None = None,
) -> str:
    if not chat_id or chat_id == "unknown":
        return ""

    initialize_database(database_path)
    context_sender = resolve_context_sender(
        database_path=database_path,
        chat_id=chat_id,
        sender_id=sender_id,
        sender_name=sender_name,
    )
    context_sender_id = context_sender["sender_id"]
    summary = get_context_summary(
        database_path=database_path,
        chat_id=chat_id,
        sender_id=context_sender_id,
    )
    cutoff = str(summary["last_message_at"]) if summary else ""
    recent_messages = get_recent_messages(
        database_path=database_path,
        chat_id=chat_id,
        sender_id=context_sender_id,
        max_chars=_recent_context_char_limit(),
        max_messages=_recent_context_message_limit(),
        cutoff=cutoff,
        settings=settings,
    )

    if not recent_messages:
        return ""

    transcript = "\n".join(
        f"{_role_label(item)}: {str(item.get('content') or '').strip()}"
        for item in recent_messages
        if str(item.get('content') or '').strip()
    )
    return ("【最近对话】\n以下消息均来自当前发问用户及机器人对该用户的回复。\n" + transcript).strip() if transcript else ""


def get_recent_messages_as_chat_history(
    *,
    database_path: Path,
    chat_id: str,
    settings: Settings | None = None,
    sender_id: str = "",
    sender_name: str = "",
    exclude_trace_id: str = "",
) -> list[dict[str, Any]]:
    if not chat_id or chat_id == "unknown":
        return []

    initialize_database(database_path)
    context_sender = resolve_context_sender(
        database_path=database_path,
        chat_id=chat_id,
        sender_id=sender_id,
        sender_name=sender_name,
    )
    context_sender_id = context_sender["sender_id"]
    summary = get_context_summary(
        database_path=database_path,
        chat_id=chat_id,
        sender_id=context_sender_id,
    )
    cutoff = str(summary["last_message_at"]) if summary else ""
    return get_recent_messages(
        database_path=database_path,
        chat_id=chat_id,
        sender_id=context_sender_id,
        max_chars=_recent_context_char_limit(),
        max_messages=_recent_context_message_limit(),
        cutoff=cutoff,
        settings=settings,
        exclude_trace_id=exclude_trace_id,
    )


def get_context_summary(*, database_path: Path, chat_id: str, sender_id: str = "") -> dict[str, Any] | None:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        row = conn.execute(
            """
            SELECT *
            FROM conversation_context_summaries
            WHERE chat_id = ?
              AND sender_id = ?
            """,
            (chat_id, _clean_sender_id(sender_id)),
        ).fetchone()
    return dict(row) if row else None


def get_recent_messages(
    *,
    database_path: Path,
    chat_id: str,
    sender_id: str = "",
    max_chars: int,
    max_messages: int,
    cutoff: str = "",
    settings: Settings | None = None,
    exclude_trace_id: str = "",
) -> list[dict[str, Any]]:
    if max_chars <= 0 or max_messages <= 0:
        return []

    initialize_database(database_path)
    context_sender_id = _clean_sender_id(sender_id)
    context_sender_like, target_sender_like = _metadata_sender_like_patterns(context_sender_id)
    fetch_multiplier = int(get_yaml_config().get("agent.recent_context_fetch_multiplier"))
    fetch_limit = max_messages * fetch_multiplier
    with connect_database(database_path) as conn:
        rows = conn.execute(
            """
            SELECT direction, sender_id, sender_name, content, created_at, reply_source, msg_type, metadata_json
            FROM chat_messages
            WHERE chat_id = ?
              AND msg_type NOT IN ('system', 'busy', 'context_summary')
              AND (? = '' OR created_at > ?)
              AND (? = '' OR sender_id = ? OR metadata_json LIKE ? OR metadata_json LIKE ?)
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (
                chat_id,
                cutoff,
                cutoff,
                context_sender_id,
                context_sender_id,
                context_sender_like,
                target_sender_like,
                fetch_limit,
            ),
        ).fetchall()

    filtered_rows = list(reversed(_filter_context_rows_for_sender(list(reversed(rows)), context_sender_id)))

    # 获取所有用户的自定义显示名
    user_ids = [str(row["sender_id"]) for row in filtered_rows if row["direction"] == "user" and row["sender_id"]]
    user_display_names = list_user_display_names(database_path, user_ids) if user_ids else {}
    
    selected: list[dict[str, Any]] = []
    used_chars = 0
    for item in filtered_rows:
        if _matches_trace_id(item, exclude_trace_id):
            continue
        content = _normalize_context_message_content(str(item.get("content") or ""), settings=settings)
        if not content:
            continue
        item["content"] = content
        # 存储用户自定义显示名，供 _role_label 使用
        if item["direction"] == "user":
            user_id = str(item.get("sender_id") or "")
            item["custom_display_name"] = user_display_names.get(user_id, "")
        content_length = len(content)
        if selected and (used_chars + content_length > max_chars or len(selected) >= max_messages):
            break
        if not selected and content_length > max_chars:
            content = smart_truncate(content, max_chars, " [消息截断]")
            item["content"] = content
            content_length = len(content)
        used_chars += content_length
        selected.append(item)
    return list(reversed(selected))


def _matches_trace_id(item: dict[str, Any], trace_id: str) -> bool:
    trace_id = str(trace_id or "").strip()
    if not trace_id:
        return False
    metadata_json = str(item.get("metadata_json") or "").strip()
    if not metadata_json:
        return False
    try:
        import json
        metadata = json.loads(metadata_json)
    except Exception:
        return False
    if not isinstance(metadata, dict):
        return False
    return str(metadata.get("trace_id") or "").strip() == trace_id


def should_compress_context(
    *,
    database_path: Path,
    chat_id: str,
    sender_id: str = "",
    settings: Settings | None = None,
) -> bool:
    if not chat_id or chat_id == "unknown":
        return False

    usage = get_context_usage(
        database_path=database_path,
        chat_id=chat_id,
        sender_id=sender_id,
        settings=settings,
        cap_per_message=False,
    )
    return usage["used_chars"] >= usage["limit_chars"]


def get_context_compression_disabled_reason(
    *,
    database_path: Path,
    chat_id: str,
) -> tuple[str, str]:
    if not chat_id or chat_id == "unknown":
        return "invalid_chat", "无效会话不触发上下文压缩"

    from app.chat_store import get_conversation
    conversation = get_conversation(chat_id=chat_id, database_path=database_path)
    if not conversation:
        return "not_found", "会话未找到"

    conversation_status = str(conversation.get("conversation_status") or "active").strip().lower()
    if conversation_status == "archived":
        return "archived", "已归档会话不触发上下文压缩"

    reply_mode = str(conversation.get("reply_mode") or "manual").strip().lower()
    if reply_mode != "ai":
        return "manual_reply", "手动回复模式不触发上下文压缩"

    return "", ""


def build_compression_transcript(
    *,
    database_path: Path,
    chat_id: str,
    sender_id: str = "",
    max_chars: int | None = None,
) -> tuple[str, int, str]:
    if max_chars is None:
        max_chars = get_yaml_config().get("agent.compression_transcript_max_chars")
    context_sender_id = _clean_sender_id(sender_id)
    context_sender_like, target_sender_like = _metadata_sender_like_patterns(context_sender_id)
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        summary = conn.execute(
            """
            SELECT summary, last_message_at
            FROM conversation_context_summaries
            WHERE chat_id = ?
              AND sender_id = ?
            """,
            (chat_id, context_sender_id),
        ).fetchone()
        cutoff = str(summary["last_message_at"]) if summary else ""
        existing_summary = str(summary["summary"] or "").strip() if summary else ""
        rows = conn.execute(
            """
            SELECT direction, sender_id, sender_name, content, created_at, reply_source, msg_type, metadata_json
            FROM chat_messages
            WHERE chat_id = ?
              AND msg_type NOT IN ('system', 'busy', 'context_summary')
              AND (? = '' OR created_at > ?)
              AND (? = '' OR sender_id = ? OR metadata_json LIKE ? OR metadata_json LIKE ?)
            ORDER BY created_at ASC
            """,
            (
                chat_id,
                cutoff,
                cutoff,
                context_sender_id,
                context_sender_id,
                context_sender_like,
                target_sender_like,
            ),
        ).fetchall()

    filtered_rows = _filter_context_rows_for_sender(rows, context_sender_id)
    
    # 获取所有用户的自定义显示名
    user_ids = [str(row["sender_id"]) for row in filtered_rows if row["direction"] == "user" and row["sender_id"]]
    user_display_names = list_user_display_names(database_path, user_ids) if user_ids else {}
    
    lines: list[str] = []
    if existing_summary:
        lines.append(f"[之前对话的上下文摘要]\n{existing_summary}")
        lines.append("[以下是摘要之后的最新对话]")
    total = len(filtered_rows)
    last_at = str(filtered_rows[-1]["created_at"]) if filtered_rows else ""
    included_count = 0
    for item in filtered_rows:
        if item["direction"] == "user":
            user_id = str(item.get("sender_id") or "")
            item["custom_display_name"] = user_display_names.get(user_id, "")
        
        line = f"{item['created_at']} {_role_label(item)}: {str(item['content']).strip()}"
        if sum(len(l) for l in lines) + len(line) > max_chars:
            lines.append("...[older or excessive content omitted]...")
            total = included_count
            last_at = str(item["created_at"]) if included_count > 0 else last_at
            break
        lines.append(line)
        included_count += 1

    return "\n".join(lines), total, last_at


def upsert_context_summary(
    *,
    database_path: Path,
    chat_id: str,
    sender_id: str,
    summary: str,
    covered_message_count: int,
    last_message_at: str,
) -> None:
    initialize_database(database_path)
    now = utc_now()
    context_sender_id = _clean_sender_id(sender_id)
    with connect_database(database_path) as conn:
        conn.execute(
            """
            INSERT INTO conversation_context_summaries (
                chat_id, sender_id, summary, covered_message_count, last_message_at,
                created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(chat_id, sender_id) DO UPDATE SET
                summary = excluded.summary,
                covered_message_count = excluded.covered_message_count,
                last_message_at = excluded.last_message_at,
                updated_at = excluded.updated_at
            """,
            (
                chat_id,
                context_sender_id,
                summary,
                covered_message_count,
                last_message_at,
                now,
                now,
            ),
        )
        conn.execute(
            """
            UPDATE conversations
            SET last_context_compressed_at = ?, updated_at = ?
            WHERE chat_id = ?
            """,
            (now, now, chat_id),
        )

    _append_context_marker(database_path=database_path, chat_id=chat_id)


def get_context_usage(
    *,
    database_path: Path,
    chat_id: str,
    sender_id: str = "",
    settings: Settings | None = None,
    cap_per_message: bool = True,
) -> dict[str, Any]:
    max_msg_chars = _context_message_max_chars()
    context_sender_id = _clean_sender_id(sender_id)
    context_sender_like, target_sender_like = _metadata_sender_like_patterns(context_sender_id)
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        summary = conn.execute(
            """
            SELECT summary, last_message_at, updated_at
            FROM conversation_context_summaries
            WHERE chat_id = ?
              AND sender_id = ?
            """,
            (chat_id, context_sender_id),
        ).fetchone()
        conversation = conn.execute(
            """
            SELECT last_context_compressed_at
            FROM conversations
            WHERE chat_id = ?
            """,
            (chat_id,),
        ).fetchone()
        cutoff = str(summary["last_message_at"]) if summary else ""
        rows = conn.execute(
            """
            SELECT direction, sender_id, content, created_at, msg_type, metadata_json
            FROM chat_messages
            WHERE chat_id = ?
              AND msg_type NOT IN ('system', 'busy', 'context_summary')
              AND (? = '' OR created_at > ?)
              AND (? = '' OR sender_id = ? OR metadata_json LIKE ? OR metadata_json LIKE ?)
            ORDER BY created_at ASC
            """,
            (
                chat_id,
                cutoff,
                cutoff,
                context_sender_id,
                context_sender_id,
                context_sender_like,
                target_sender_like,
            ),
        ).fetchall()
    summary_chars = len(str(summary["summary"] or "")) if summary else 0
    filtered_rows = _filter_context_rows_for_sender(rows, context_sender_id)
    if cap_per_message and max_msg_chars > 0:
        message_chars = sum(min(len(str(row.get("content") or "")), max_msg_chars) for row in filtered_rows)
    else:
        message_chars = sum(len(str(row.get("content") or "")) for row in filtered_rows)
    return {
        "used_chars": summary_chars + message_chars,
        "limit_chars": _resolve_context_char_limit(settings),
        "compressed": bool(summary),
        "summary_chars": summary_chars,
        "message_chars": message_chars,
        "summary_updated_at": str(summary["updated_at"]) if summary else "",
        "last_context_compressed_at": str(conversation["last_context_compressed_at"]) if conversation else "",
    }


def batch_get_context_usage(
    *,
    database_path: Path,
    chat_ids: list[str],
    sender_ids_by_chat_id: dict[str, str] | None = None,
    settings: Settings | None = None,
) -> dict[str, dict[str, Any]]:
    if not chat_ids:
        return {}
    initialize_database(database_path)
    sender_map = sender_ids_by_chat_id or {}
    result: dict[str, dict[str, Any]] = {}
    for cid in chat_ids:
        context_sender = resolve_context_sender(
            database_path=database_path,
            chat_id=cid,
            sender_id=sender_map.get(cid, ""),
        )
        result[cid] = get_context_usage(
            database_path=database_path,
            chat_id=cid,
            sender_id=context_sender["sender_id"],
            settings=settings,
            cap_per_message=False,
        )
    return result


def _resolve_context_char_limit(settings: Settings | None) -> int:
    default = get_yaml_config().get("agent.context_length_limit")
    if settings is None:
        return default
    value = int(getattr(settings.agent.context, "compression_trigger_chars", 0) or 0)
    return value if value > 0 else default


def _recent_context_char_limit() -> int:
    return int(get_yaml_config().get("agent.recent_context_max_chars"))


def _recent_context_message_limit() -> int:
    return int(get_yaml_config().get("agent.recent_context_max_messages"))


def _context_message_max_chars() -> int:
    return int(get_yaml_config().get("agent.context_message_max_chars"))


def _summary_in_prompt_max_chars(settings: Settings | None) -> int:
    # 直接使用 agent.summary_in_prompt_max_chars 配置
    default = int(get_yaml_config().get("agent.summary_in_prompt_max_chars"))
    return default


def _normalize_context_message_content(content: str, *, settings: Settings | None = None) -> str:
    from app.chat_store import sanitize_chat_message_content

    text = str(content or "").strip()
    if not text:
        return ""
    text = sanitize_chat_message_content(text, direction="bot")
    reply_notice = ""
    if settings is not None:
        reply_notice = str(getattr(settings.agent, "reply_notice", "") or "").strip()
    if reply_notice:
        text = str(text).replace(f"\n\n({reply_notice})", "").replace(reply_notice, "").strip()
    max_chars = _context_message_max_chars()
    if max_chars > 0 and len(text) > max_chars:
        text = smart_truncate(text, max_chars, " [内容截断]")
    return text


def _append_context_marker(*, database_path: Path, chat_id: str) -> None:
    from app.chat_store import append_chat_message, get_conversation

    conversation = get_conversation(chat_id=chat_id, database_path=database_path)
    if not conversation:
        return

    append_chat_message(
        direction="system",
        chat_id=chat_id,
        chat_name=str(conversation.get("chat_name") or chat_id),
        sender_id="system",
        sender_name="上下文系统",
        content="本对话上下文已压缩",
        msg_type="context_summary",
        database_path=database_path,
        reply_source="system",
        bot_key=str(conversation.get("bot_key") or ""),
        external_chat_id=str(conversation.get("external_chat_id") or ""),
        conversation_kind=str(conversation.get("conversation_kind") or "external"),
    )


def _role_label(item: dict[str, Any]) -> str:
    direction = str(_item_value(item, "direction") or "")
    if direction == "user":
        # 用户优先使用自定义显示名，如果没有则使用 sender_name
        custom_display_name = str(_item_value(item, "custom_display_name") or "").strip()
        if custom_display_name:
            return custom_display_name
        return str(_item_value(item, "sender_name") or "用户")
    if direction == "bot":
        # Bot 明确显示是手动回复还是智能回复
        reply_source = str(_item_value(item, "reply_source") or "").strip().lower()
        if reply_source == "manual":
            return "手动回复"
        else:
            return "智能回复"
    return direction or "消息"
