from __future__ import annotations

"""聊天消息存储与会话管理模块。

管理聊天消息的存储、检索和会话生命周期，包括消息追加、内容清洗、
会话的创建/删除/归档/置顶、显示名管理、未读计数和回复模式设置等。
"""

import ast
import contextlib
import json
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.db.core import connect_database, initialize_database
from app.logger import get_logger
from app.utils import resolve_database_path, utc_now

_COMMAND_WRAPPER_PREFIXES = ("Command(update=", "Command(", "AIMessage(", "HumanMessage(")


@dataclass(slots=True)
class ChatMessage:
    id: str
    created_at: str
    direction: str
    chat_id: str
    chat_name: str
    sender_id: str
    sender_name: str
    content: str
    msg_type: str
    status: str = "sent"
    reply_status: str = "unreplied"
    reply_source: str = ""
    bot_key: str = ""
    external_chat_id: str = ""
    conversation_kind: str = "external"
    metadata: dict[str, Any] | None = None


def append_chat_message(
    *,
    direction: str,
    chat_id: str,
    chat_name: str,
    sender_id: str,
    sender_name: str,
    content: str,
    msg_type: str,
    status: str = "sent",
    database_path: Path | None = None,
    reply_source: str = "",
    bot_key: str = "",
    external_chat_id: str = "",
    conversation_kind: str = "external",
    chat_type: str = "unknown",
    metadata: dict[str, Any] | None = None,
    mark_user_replied: bool = True,
    context_sender_id: str = "",
    display_name: str | None = None,
) -> ChatMessage:
    """追加一条聊天消息到数据库，并更新对应的会话信息。

    对消息内容进行清洗后写入数据库，同时更新或创建对应的会话记录，
    如果是 Bot 回复消息，还会标记最近一条用户消息为已回复。

    Args:
        direction: 消息方向，"user" 或 "bot"。
        chat_id: 会话 ID。
        chat_name: 会话名称。
        sender_id: 发送者 ID。
        sender_name: 发送者名称。
        content: 消息内容。
        msg_type: 消息类型。
        status: 消息状态，默认为 "sent"。
        database_path: 数据库路径，默认为 None。
        reply_source: 回复来源标识。
        bot_key: 所属 Bot 的标识。
        external_chat_id: 外部会话 ID。
        conversation_kind: 会话类型，默认为 "external"。
        chat_type: 聊天类型，默认为 "unknown"。
        metadata: 消息元数据。
        mark_user_replied: 是否标记用户消息为已回复，默认为 True。
        display_name: 会话显示名称。

    Returns:
        创建的 ChatMessage 对象。
    """
    normalized_content = sanitize_chat_message_content(content, direction=direction)
    message_metadata = dict(metadata or {})
    clean_context_sender_id = str(context_sender_id or "").strip()
    if direction == "bot" and clean_context_sender_id:
        message_metadata.setdefault("context_sender_id", clean_context_sender_id)
    message = ChatMessage(
        id=uuid4().hex,
        created_at=utc_now(),
        direction=direction,
        chat_id=chat_id,
        chat_name=chat_name,
        sender_id=sender_id,
        sender_name=sender_name,
        content=normalized_content,
        msg_type=msg_type,
        status=status,
        reply_status="unreplied" if direction == "user" else "replied",
        reply_source=reply_source or _default_reply_source(direction, msg_type),
        bot_key=bot_key,
        external_chat_id=external_chat_id or chat_id,
        conversation_kind=conversation_kind or "external",
        metadata=message_metadata,
    )
    db_path = resolve_database_path(database_path)
    initialize_database(db_path)

    with connect_database(db_path) as conn:
        conversation_sender_id = sender_id if direction == "user" else ""
        conversation_sender_name = sender_name if direction == "user" else ""
        _upsert_conversation(
            conn,
            chat_id=chat_id,
            chat_name=chat_name,
            sender_id=conversation_sender_id,
            sender_name=conversation_sender_name,
            last_message_at=message.created_at,
            bot_key=message.bot_key,
            external_chat_id=message.external_chat_id,
            conversation_kind=message.conversation_kind,
            chat_type=chat_type,
            unread_delta=1 if direction == "user" else 0,
            display_name=display_name,
        )
        conn.execute(
            """
            INSERT INTO chat_messages (
                id, created_at, direction, chat_id, chat_name, sender_id,
                sender_name, content, msg_type, status, reply_status, reply_source,
                bot_key, external_chat_id, conversation_kind, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                message.id,
                message.created_at,
                message.direction,
                message.chat_id,
                message.chat_name,
                message.sender_id,
                message.sender_name,
                message.content,
                message.msg_type,
                message.status,
                message.reply_status,
                message.reply_source,
                message.bot_key,
                message.external_chat_id,
                message.conversation_kind,
                json.dumps(message.metadata or {}, ensure_ascii=False, sort_keys=True),
            ),
        )
        if direction == "bot" and mark_user_replied:
            mark_latest_user_message_replied(
                chat_id=chat_id,
                database_path=db_path,
                conn=conn,
                sender_id=clean_context_sender_id,
            )
    return message


def sanitize_chat_message_content(content: str, *, direction: str = "") -> str:
    """清洗聊天消息内容，提取可见文本并去除推理块等包装。

    对于 Bot 方向的消息，会尝试从 AIMessage/Command 等包装结构中
    提取可见内容，并移除推理块（reasoning_content）。

    Args:
        content: 原始消息内容。
        direction: 消息方向，"user" 或 "bot"。

    Returns:
        清洗后的消息内容。
    """
    text = str(content or "")
    if not text.strip():
        return ""

    sanitized = text.strip()
    if direction == "bot":
        extracted = _extract_visible_message_content(sanitized)
        if extracted:
            sanitized = extracted
        sanitized = _strip_reasoning_blocks(sanitized)

    return sanitized.strip()


def _extract_visible_message_content(text: str) -> str:
    if not text.startswith(_COMMAND_WRAPPER_PREFIXES) and "reasoning_content" not in text:
        return text

    matches = list(
        re.finditer(
            r"AIMessage\(content=(?P<quote>['\"])(?P<body>.*?)(?P=quote),\s*additional_kwargs=",
            text,
            re.DOTALL,
        )
    )
    if not matches:
        matches = list(
            re.finditer(
                r"content=(?P<quote>['\"])(?P<body>.*?)(?P=quote)(?:,\s*[a-zA-Z_]+=|\))",
                text,
                re.DOTALL,
            )
        )
    for match in reversed(matches):
        body = str(match.group("body") or "")
        unescaped = _safe_unescape_python_string(body)
        if unescaped.strip():
            return unescaped.strip()
    return text


def _strip_reasoning_blocks(text: str) -> str:
    cleaned = re.sub(
        r"additional_kwargs=\{.*?reasoning_content.*?\}(?:,\s*response_metadata=\{.*?\})?",
        "",
        text,
        flags=re.DOTALL,
    )
    cleaned = cleaned.replace("Command(update=", "").replace("))", ")")
    return cleaned.strip()


def _safe_unescape_python_string(text: str) -> str:
    try:
        return ast.literal_eval(f"'{text}'")
    except Exception:
        try:
            return bytes(text, "utf-8").decode("unicode_escape")
        except Exception:
            return text


def read_chat_messages(
    limit: int = 500,
    database_path: Path | None = None,
    bot_key: str = "",
    conversation_kind: str = "",
    offset: int = 0,
    chat_ids: list[str] | None = None,
) -> list[dict[str, Any]]:
    db_path = resolve_database_path(database_path)
    initialize_database(db_path)

    clauses = ["COALESCE(c.deleted_at, '') = ''"]
    params: list[Any] = []
    if bot_key:
        clauses.append("COALESCE(m.bot_key, c.bot_key, 'default') = ?")
        params.append(bot_key)
    if conversation_kind:
        clauses.append("COALESCE(m.conversation_kind, c.conversation_kind, 'external') = ?")
        params.append(conversation_kind)
    clean_chat_ids = [str(chat_id or "").strip() for chat_id in (chat_ids or []) if str(chat_id or "").strip()]
    if clean_chat_ids:
        placeholders = ",".join("?" for _ in clean_chat_ids)
        clauses.append(f"m.chat_id IN ({placeholders})")
        params.extend(clean_chat_ids)

    params.append(limit)
    params.append(max(0, offset))
    with connect_database(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT
                m.id,
                m.created_at,
                m.direction,
                m.chat_id,
                COALESCE(NULLIF(c.display_name, ''), m.chat_name) AS chat_name,
                c.display_name,
                c.chat_type,
                c.bot_key,
                c.external_chat_id,
                c.conversation_kind,
                c.pinned,
                c.pin_rank,
                c.unread_count,
                c.reply_mode,
                c.last_context_compressed_at,
                m.sender_id,
                m.sender_name,
                m.content,
                m.msg_type,
                m.status,
                m.reply_status,
                m.reply_source,
                m.metadata_json
            FROM chat_messages AS m
            LEFT JOIN conversations AS c ON c.chat_id = m.chat_id
            WHERE {' AND '.join(clauses)}
            ORDER BY m.created_at DESC
            LIMIT ? OFFSET ?
            """,
            params,
        ).fetchall()

    return [_row_to_message(row) for row in reversed(rows)]


def get_latest_messages_for_chats(
    *,
    chat_ids: list[str],
    database_path: Path | None = None,
) -> dict[str, dict[str, Any]]:
    clean_chat_ids = [str(chat_id or "").strip() for chat_id in chat_ids if str(chat_id or "").strip()]
    if not clean_chat_ids:
        return {}

    db_path = resolve_database_path(database_path)
    initialize_database(db_path)
    placeholders = ",".join("?" for _ in clean_chat_ids)
    with connect_database(db_path) as conn:
        rows = conn.execute(
            f"""
            SELECT m.*
            FROM chat_messages AS m
            JOIN (
                SELECT chat_id, MAX(created_at) AS latest_created_at
                FROM chat_messages
                WHERE chat_id IN ({placeholders})
                GROUP BY chat_id
            ) AS latest
              ON latest.chat_id = m.chat_id
             AND latest.latest_created_at = m.created_at
            ORDER BY m.created_at DESC
            """,
            clean_chat_ids,
        ).fetchall()

    latest_messages: dict[str, dict[str, Any]] = {}
    for row in rows:
        item = _row_to_message(row)
        chat_id = str(item.get("chat_id") or "").strip()
        if chat_id and chat_id not in latest_messages:
            latest_messages[chat_id] = item
    return latest_messages


def get_latest_user_message_trace_id(
    *,
    chat_id: str,
    database_path: Path,
) -> str:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        rows = conn.execute(
            """
            SELECT metadata_json
            FROM chat_messages
            WHERE chat_id = ?
              AND direction = 'user'
            ORDER BY
                CASE WHEN reply_status = 'unreplied' THEN 0 ELSE 1 END,
                created_at DESC
            LIMIT 20
            """,
            (chat_id,),
        ).fetchall()
    for row in rows:
        metadata_json = str(row["metadata_json"] or "").strip()
        if not metadata_json:
            continue
        try:
            metadata = json.loads(metadata_json)
        except json.JSONDecodeError:
            get_logger("chat_store").warning(
                "metadata_json 解析失败，跳过该行",
                extra={"raw_preview": metadata_json[:200]},
            )
            continue
        trace_id = str(metadata.get("trace_id") or "").strip()
        if trace_id:
            return trace_id
    return ""


def get_last_unreplied_user_message(
    *,
    chat_id: str,
    database_path: Path,
) -> dict[str, str]:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        row = conn.execute(
            """
            SELECT content, sender_id, sender_name, created_at
            FROM chat_messages
            WHERE chat_id = ?
              AND direction = 'user'
              AND reply_status = 'unreplied'
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
        "sender_id": str(row["sender_id"] or ""),
        "sender_name": str(row["sender_name"] or ""),
        "created_at": str(row["created_at"] or ""),
    }


def update_conversation_display_name(
    *,
    chat_id: str,
    display_name: str,
    database_path: Path,
) -> dict[str, Any]:
    initialize_database(database_path)
    now = utc_now()
    
    # 先获取会话信息，判断是否是用户类型会话
    conversation = None
    with connect_database(database_path) as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        if row:
            conversation = dict(row)
    
    # 用户级会话只有用户名这一层显示名；群聊和“我--bot”保留独立会话名。
    if conversation:
        chat_type = str(conversation.get("chat_type") or "")
        conversation_kind = str(conversation.get("conversation_kind") or "")
        sender_id = str(conversation.get("sender_id") or "").strip()
        if (chat_type not in ("group", "room") 
            and conversation_kind != "me" 
            and sender_id):
            from app.db.user_store import update_user_display_name
            update_user_display_name(database_path, user_id=sender_id, display_name=display_name)
    
    # 更新会话显示名
    with connect_database(database_path) as conn:
        if conversation is None:
            conn.execute(
                """
                INSERT INTO conversations (
                    chat_id, chat_name, display_name, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?)
                """,
                (chat_id, chat_id, display_name, now, now),
            )
        else:
            conn.execute(
                """
                UPDATE conversations
                SET display_name = ?, updated_at = ?
                WHERE chat_id = ?
                """,
                (display_name, now, chat_id),
            )

    return get_conversation(chat_id=chat_id, database_path=database_path)


def get_conversation(*, chat_id: str, database_path: Path) -> dict[str, Any] | None:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        row = conn.execute(
            "SELECT * FROM conversations WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
    return dict(row) if row else None


def list_conversations(
    *,
    database_path: Path,
    bot_key: str = "",
    keyword: str = "",
    page: int = 1,
    page_size: int = 50,
) -> dict[str, Any]:
    initialize_database(database_path)
    page = max(1, page)
    page_size = max(1, min(page_size, 100))
    offset = (page - 1) * page_size
    clauses = ["deleted_at = ''"]
    params: list[Any] = []

    if bot_key:
        clauses.append("bot_key = ?")
        params.append(bot_key)
    if keyword:
        escaped = str(keyword).replace("\\", "\\\\").replace("%", "\\%").replace("_", "\\_")
        clauses.append("(chat_name LIKE ? ESCAPE '\\' OR display_name LIKE ? ESCAPE '\\' OR external_chat_id LIKE ? ESCAPE '\\')")
        pattern = f"%{escaped}%"
        params.extend([pattern, pattern, pattern])

    where_sql = " AND ".join(clauses)
    with connect_database(database_path) as conn:
        total = int(
            conn.execute(
                f"SELECT COUNT(*) AS count FROM conversations WHERE {where_sql}",
                params,
            ).fetchone()["count"]
        )
        rows = conn.execute(
            f"""
            SELECT *
            FROM conversations
            WHERE {where_sql}
            ORDER BY
                CASE WHEN COALESCE(conversation_status, 'active') = 'active' THEN 0 ELSE 1 END,
                pinned DESC, pin_rank DESC,
                COALESCE(NULLIF(last_message_at, ''), created_at) DESC
            LIMIT ? OFFSET ?
            """,
            [*params, page_size, offset],
        ).fetchall()

    return {
        "items": [dict(row) for row in rows],
        "page": page,
        "page_size": page_size,
        "total": total,
    }


def delete_conversations(*, chat_ids: list[str], database_path: Path) -> int:
    ids = [chat_id for chat_id in chat_ids if chat_id and chat_id != "unknown"]
    if not ids:
        return 0

    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        user_rows = conn.execute(
            f"""
            SELECT DISTINCT sender_id
            FROM conversations
            WHERE chat_id IN ({','.join('?' for _ in ids)})
              AND sender_id != ''
              AND chat_type NOT IN ('group', 'room')
              AND conversation_kind != 'me'
            """,
            ids,
        ).fetchall()
        user_ids = [str(row["sender_id"] or "").strip() for row in user_rows if str(row["sender_id"] or "").strip()]
        me_rows = conn.execute(
            f"SELECT chat_id FROM conversations WHERE chat_id IN ({','.join('?' for _ in ids)}) AND conversation_kind = 'me'",
            ids,
        ).fetchall()
        if me_rows:
            me_ids = {row["chat_id"] for row in me_rows}
            ids = [cid for cid in ids if cid not in me_ids]
            if not ids:
                return 0
        placeholders = ",".join("?" for _ in ids)
        cursor = conn.execute(
            f"""
            UPDATE conversations
            SET deleted_at = ?,
                display_name = CASE
                    WHEN chat_type IN ('group', 'room') THEN ''
                    ELSE display_name
                END,
                updated_at = ?
            WHERE chat_id IN ({placeholders})
            """,
            [now, now, *ids],
        )
        conn.execute(
            f"""
            DELETE FROM conversation_context_summaries
            WHERE chat_id IN ({placeholders})
            """,
            list(ids),
        )
        for user_id in user_ids:
            remaining = conn.execute(
                """
                SELECT 1
                FROM conversations
                WHERE sender_id = ?
                  AND deleted_at = ''
                  AND chat_type NOT IN ('group', 'room')
                  AND conversation_kind != 'me'
                LIMIT 1
                """,
                (user_id,),
            ).fetchone()
            if remaining is None:
                conn.execute("DELETE FROM user_profile WHERE user_id = ?", (user_id,))
                conn.execute(
                    """
                    UPDATE conversations
                    SET display_name = '', updated_at = ?
                    WHERE sender_id = ?
                      AND chat_type NOT IN ('group', 'room')
                      AND conversation_kind != 'me'
                    """,
                    (now, user_id),
                )
    return int(cursor.rowcount or 0)


def set_conversation_pinned(
    *,
    chat_id: str,
    pinned: bool,
    database_path: Path,
) -> dict[str, Any]:
    initialize_database(database_path)
    now = utc_now()
    pin_rank = 100 if pinned else 0
    with connect_database(database_path) as conn:
        current = conn.execute(
            "SELECT conversation_kind FROM conversations WHERE chat_id = ?",
            (chat_id,),
        ).fetchone()
        if current and str(current["conversation_kind"]) == "me":
            pinned = True
            pin_rank = 1000000000
        conn.execute(
            """
            UPDATE conversations
            SET pinned = ?, pin_rank = ?, updated_at = ?
            WHERE chat_id = ?
            """,
            (int(pinned), pin_rank, now, chat_id),
        )
    return get_conversation(chat_id=chat_id, database_path=database_path)


def mark_conversation_read(*, chat_id: str, database_path: Path) -> None:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        conn.execute(
            "UPDATE conversations SET unread_count = 0, updated_at = ? WHERE chat_id = ?",
            (now, chat_id),
        )


def mark_all_bot_conversations_read(*, bot_key: str, database_path: Path) -> int:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        cursor = conn.execute(
            "UPDATE conversations SET unread_count = 0, updated_at = ? WHERE bot_key = ? AND deleted_at = '' AND unread_count > 0",
            (now, bot_key),
        )
    return int(cursor.rowcount or 0)


def list_active_bot_conversations(*, bot_key: str, database_path: Path) -> list[dict[str, Any]]:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        rows = conn.execute(
            """
            SELECT chat_id, chat_name, display_name, external_chat_id, conversation_kind, chat_type
            FROM conversations
            WHERE bot_key = ?
              AND deleted_at = ''
              AND COALESCE(conversation_status, 'active') = 'active'
            ORDER BY pinned DESC, pin_rank DESC, COALESCE(NULLIF(last_message_at, ''), created_at) DESC
            """,
            (bot_key,),
        ).fetchall()
    return [dict(row) for row in rows]


def set_conversation_reply_mode(
    *,
    chat_id: str,
    reply_mode: str,
    database_path: Path,
) -> dict[str, Any]:
    if reply_mode not in ("manual", "ai"):
        raise ValueError("reply_mode 必须是 'manual' 或 'ai'")
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        conn.execute(
            "UPDATE conversations SET reply_mode = ?, updated_at = ? WHERE chat_id = ?",
            (reply_mode, now, chat_id),
        )
    return get_conversation(chat_id=chat_id, database_path=database_path)


def get_bot_unread_total(*, bot_key: str, database_path: Path) -> int:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        row = conn.execute(
            "SELECT COALESCE(SUM(unread_count), 0) AS total FROM conversations WHERE bot_key = ? AND deleted_at = ''",
            (bot_key,),
        ).fetchone()
    return int(row["total"] if row else 0)


def mark_latest_user_message_replied(
    *,
    chat_id: str,
    database_path: Path,
    conn=None,
    sender_id: str = "",
) -> None:
    owns_connection = conn is None
    if owns_connection:
        initialize_database(database_path)
    with connect_database(database_path) if owns_connection else contextlib.nullcontext(conn) as connection:
        connection.execute(
            """
            UPDATE chat_messages
            SET reply_status = 'replied'
            WHERE id = (
                SELECT id
                FROM chat_messages
                WHERE chat_id = ?
                  AND direction = 'user'
                  AND reply_status = 'unreplied'
                  AND (? = '' OR sender_id = ?)
                ORDER BY created_at DESC
                LIMIT 1
            )
            """,
            (chat_id, sender_id, sender_id),
        )


def _upsert_conversation(
    conn,
    *,
    chat_id: str,
    chat_name: str,
    sender_id: str,
    sender_name: str,
    last_message_at: str,
    bot_key: str = "",
    external_chat_id: str = "",
    conversation_kind: str = "external",
    chat_type: str = "unknown",
    unread_delta: int = 0,
    reply_mode: str = "manual",
    display_name: str | None = None,
) -> None:
    now = utc_now()
    effective_chat_type = chat_type or "unknown"
    is_user_conversation = (
        effective_chat_type not in ("group", "room")
        and conversation_kind != "me"
        and str(sender_id or "").strip()
    )
    user_profile_display_name = ""
    existing_user_display_name = ""
    if is_user_conversation:
        profile_row = conn.execute(
            "SELECT display_name FROM user_profile WHERE user_id = ?",
            (str(sender_id).strip(),),
        ).fetchone()
        if profile_row:
            user_profile_display_name = str(profile_row["display_name"] or "").strip()
        existing_row = conn.execute(
            """
            SELECT display_name
            FROM conversations
            WHERE sender_id = ?
              AND chat_type NOT IN ('group', 'room')
              AND conversation_kind != 'me'
              AND deleted_at = ''
              AND COALESCE(display_name, '') != ''
            ORDER BY COALESCE(NULLIF(created_at, ''), updated_at) ASC
            LIMIT 1
            """,
            (str(sender_id).strip(),),
        ).fetchone()
        if existing_row:
            existing_user_display_name = str(existing_row["display_name"] or "").strip()
    
    # 优先使用传入的 display_name，如果是企微 ID 则忽略
    effective_display_name = None
    if user_profile_display_name:
        effective_display_name = user_profile_display_name
    elif existing_user_display_name:
        effective_display_name = existing_user_display_name
    elif is_user_conversation and display_name and _looks_like_wecom_id(display_name) is False:
        effective_display_name = display_name
    elif conversation_kind == "me" and display_name:
        effective_display_name = display_name
    
    if not effective_display_name:
        effective_display_name = _default_display_name(
            chat_type=effective_chat_type,
            conversation_kind=conversation_kind,
            chat_name=chat_name,
            sender_id=sender_id,
            external_chat_id=external_chat_id,
            created_at=now,
        )
    if is_user_conversation and not user_profile_display_name and effective_display_name:
        conn.execute(
            """
            INSERT INTO user_profile (user_id, display_name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                display_name = COALESCE(NULLIF(user_profile.display_name, ''), excluded.display_name),
                updated_at = excluded.updated_at
            """,
            (str(sender_id).strip(), effective_display_name, now, now),
        )
    effective_chat_name = effective_display_name if is_user_conversation and effective_display_name else (chat_name or chat_id)
    
    effective_reply_mode = reply_mode if reply_mode in ("manual", "ai") else "manual"
    
    # 先检查现有记录，判断是否需要更新 display_name
    need_update_display_name = False
    cursor = conn.execute(
        "SELECT display_name, deleted_at FROM conversations WHERE chat_id = ?",
        (chat_id,),
    )
    row = cursor.fetchone()
    existing_display_name = str(row["display_name"] or "") if row else ""
    was_deleted = bool(str(row["deleted_at"] or "").strip()) if row else False
    
    # 判断是否需要更新 display_name
    if row:
        # 如果现有 display_name 为空或看起来像企微 ID，且我们有新的有效 display_name，则更新
        if effective_display_name and (not existing_display_name or _looks_like_wecom_id(existing_display_name)):
            need_update_display_name = True
    
    conn.execute(
        """
        INSERT INTO conversations (
            chat_id, chat_name, display_name, chat_type, sender_id, sender_name, last_message_at,
            bot_key, external_chat_id, conversation_kind, unread_count, reply_mode,
            created_at, updated_at
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        ON CONFLICT(chat_id) DO UPDATE SET
            chat_name = excluded.chat_name,
            display_name = CASE
                WHEN ? THEN excluded.display_name
                ELSE COALESCE(NULLIF(conversations.display_name, ''), excluded.display_name)
            END,
            chat_type = CASE
                WHEN excluded.chat_type != '' AND excluded.chat_type != 'unknown' THEN excluded.chat_type
                ELSE conversations.chat_type
            END,
            sender_id = CASE
                WHEN excluded.sender_id != '' THEN excluded.sender_id
                ELSE conversations.sender_id
            END,
            sender_name = CASE
                WHEN excluded.sender_name != '' THEN excluded.sender_name
                ELSE conversations.sender_name
            END,
            last_message_at = excluded.last_message_at,
            bot_key = COALESCE(NULLIF(conversations.bot_key, ''), excluded.bot_key),
            external_chat_id = excluded.external_chat_id,
            conversation_kind = excluded.conversation_kind,
            unread_count = MAX(MIN(conversations.unread_count + ?, 999), 0),
            reply_mode = CASE
                WHEN ? THEN 'manual'
                ELSE COALESCE(NULLIF(conversations.reply_mode, ''), 'manual')
            END,
            conversation_status = 'active',
            deleted_at = '',
            last_send_error = '',
            updated_at = excluded.updated_at
        """,
        (
            chat_id,
            effective_chat_name,
            effective_display_name,
            effective_chat_type,
            sender_id,
            sender_name,
            last_message_at,
            bot_key,
            external_chat_id or chat_id,
            conversation_kind or "external",
            unread_delta,
            effective_reply_mode,
            now,
            now,
            need_update_display_name,
            unread_delta,
            was_deleted,
        ),
    )


def _default_display_name(
    *,
    chat_type: str,
    conversation_kind: str,
    chat_name: str,
    sender_id: str,
    external_chat_id: str,
    created_at: str,
) -> str:
    if conversation_kind == "me":
        return chat_name or "我"
    if chat_type in {"group", "room"}:
        return ""
    return _conversation_label("用户", sender_id or external_chat_id or chat_name, created_at)


def _conversation_label(kind: str, seed: str, created_at: str) -> str:
    return f"{kind} {_time_token(created_at)} {_stable_suffix(seed)}"


def _time_token(value: str) -> str:
    text = str(value or "").strip()
    try:
        dt = datetime.fromisoformat(text)
    except ValueError:
        return "0000-0000"
    if dt.tzinfo is not None:
        dt = dt.astimezone()
    return dt.strftime("%m%d-%H%M")


def _stable_suffix(value: str, length: int = 4) -> str:
    text = str(value or "").strip()
    if not text:
        return "0000"
    hash_value = 0
    for char in text:
        hash_value = ((hash_value * 131) + ord(char)) & 0xFFFFFFFF
    return f"{hash_value:0{length}X}"[:length]


def _looks_like_wecom_id(value: str) -> bool:
    if not value or not isinstance(value, str):
        return False
    import re
    # 匹配企微 ID 格式
    pattern1 = re.compile(r"^(wo|wm|wb|wr)[A-Za-z0-9_-]{12,}$")
    pattern2 = re.compile(r"^[A-Za-z0-9_-]{24,}$")
    return bool(pattern1.match(value) or pattern2.match(value))


def _row_to_message(row) -> dict[str, Any]:
    item = dict(row)
    try:
        item["metadata"] = json.loads(str(item.pop("metadata_json") or "{}"))
    except json.JSONDecodeError:
        get_logger("chat_store").warning(
            "metadata_json 解析失败，降级为空对象",
            extra={"raw_preview": str(item.get("id", ""))[:100]},
        )
        item["metadata"] = {}
    return item


def _default_reply_source(direction: str, msg_type: str) -> str:
    if direction == "user":
        return "user"
    if msg_type == "manual":
        return "manual"
    if msg_type == "agent":
        return "ai"
    if msg_type == "busy":
        return "system"
    return msg_type or direction


def set_conversation_archived(
    *,
    chat_id: str,
    database_path: Path,
) -> dict[str, Any]:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        conn.execute(
            """
            UPDATE conversations
            SET conversation_status = 'archived', reply_mode = 'manual', updated_at = ?
            WHERE chat_id = ?
            """,
            (now, chat_id),
        )
    return get_conversation(chat_id=chat_id, database_path=database_path)


def set_conversation_unarchived(
    *,
    chat_id: str,
    database_path: Path,
) -> dict[str, Any]:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        conn.execute(
            """
            UPDATE conversations
            SET conversation_status = 'active', updated_at = ?
            WHERE chat_id = ?
            """,
            (now, chat_id),
        )
    return get_conversation(chat_id=chat_id, database_path=database_path)


def set_conversation_send_error(
    *,
    chat_id: str,
    error: str,
    database_path: Path,
) -> None:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        conn.execute(
            """
            UPDATE conversations
            SET last_send_error = ?, reply_mode = 'manual', updated_at = ?
            WHERE chat_id = ?
            """,
            (error, now, chat_id),
        )


def clear_conversation_send_error(*, chat_id: str, database_path: Path) -> None:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        conn.execute(
            """
            UPDATE conversations
            SET last_send_error = '', updated_at = ?
            WHERE chat_id = ?
            """,
            (now, chat_id),
        )


def get_chat_history_by_id(
    *,
    chat_id: str,
    database_path: Path,
    limit: int = 100,
) -> list[dict[str, Any]]:
    """
    获取特定 chat_id 的完整对话历史，按时间正序排列
    
    Args:
        chat_id: 聊天ID
        database_path: 数据库路径
        limit: 最大消息数量限制
    
    Returns:
        对话消息列表，按时间正序排列
    """
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        rows = conn.execute(
            """
            SELECT
                m.id,
                m.created_at,
                m.direction,
                m.chat_id,
                COALESCE(NULLIF(c.display_name, ''), m.chat_name) AS chat_name,
                m.sender_id,
                m.sender_name,
                m.content,
                m.msg_type,
                m.status,
                m.reply_status,
                m.reply_source,
                m.metadata_json
            FROM chat_messages AS m
            LEFT JOIN conversations AS c ON c.chat_id = m.chat_id
            WHERE m.chat_id = ?
              AND COALESCE(c.deleted_at, '') = ''
            ORDER BY m.created_at ASC
            LIMIT ?
            """,
            (chat_id, limit),
        ).fetchall()

    return [_row_to_message(row) for row in rows]


def format_chat_history(chat_messages: list[dict[str, Any]]) -> str:
    """
    将对话历史格式化为文本字符串
    
    Args:
        chat_messages: 对话消息列表
    
    Returns:
        格式化的对话历史字符串
    """
    if not chat_messages:
        return ""
    
    formatted_lines = []
    for msg in chat_messages:
        direction = msg.get("direction", "")
        sender_name = msg.get("sender_name", "")
        content = msg.get("content", "")
        
        if direction == "user":
            formatted_lines.append(f"用户: {content}")
        elif direction == "bot":
            formatted_lines.append(f"AI助手: {content}")
        else:
            formatted_lines.append(f"{sender_name}: {content}")
    
    return "\n".join(formatted_lines)
