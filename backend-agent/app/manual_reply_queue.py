from __future__ import annotations

"""手动回复队列模块。

实现管理员发起的手动回复消息队列，支持回复命令的入队、出队、
状态标记和查询，用于将管理控制台的手动回复指令传递给 Bot 进程执行发送。
"""

import json
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.db.core import connect_database, initialize_database
from app.logger import get_logger
from app.utils import resolve_database_path, utc_now

logger = get_logger("manual_reply_queue")


@dataclass(slots=True)
class ManualReplyCommand:
    id: str
    created_at: str
    chat_id: str
    chat_name: str
    content: str
    status: str = "pending"
    error: str = ""
    bot_key: str = ""
    conversation_chat_id: str = ""
    external_chat_id: str = ""
    metadata: dict[str, Any] | None = None


def enqueue_manual_reply(
    *,
    chat_id: str,
    chat_name: str,
    content: str,
    database_path: Path | None = None,
    bot_key: str = "",
    conversation_chat_id: str = "",
    external_chat_id: str = "",
    metadata: dict[str, Any] | None = None,
    skip_record: bool = False,
) -> ManualReplyCommand:
    db_path = resolve_database_path(database_path)
    initialize_database(db_path)
    now = utc_now()
    meta = dict(metadata or {})
    if skip_record:
        meta["skip_record"] = True
    command = ManualReplyCommand(
        id=uuid4().hex,
        created_at=now,
        chat_id=chat_id,
        chat_name=chat_name,
        content=content,
        bot_key=bot_key,
        conversation_chat_id=conversation_chat_id or chat_id,
        external_chat_id=external_chat_id or chat_id,
        metadata=meta,
    )
    with connect_database(db_path) as conn:
        conn.execute(
            """
            INSERT INTO manual_reply_commands (
                id, created_at, updated_at, chat_id, chat_name, content, status, error,
                bot_key, conversation_chat_id, external_chat_id, metadata_json
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, '', ?, ?, ?, ?)
            """,
            (
                command.id,
                command.created_at,
                now,
                command.chat_id,
                command.chat_name,
                command.content,
                command.status,
                command.bot_key,
                command.conversation_chat_id,
                command.external_chat_id,
                json.dumps(command.metadata or {}, ensure_ascii=False, sort_keys=True),
            ),
        )
    return command


def read_manual_replies(
    database_path: Path | None = None,
    *,
    limit: int = 100,
    offset: int = 0,
) -> list[dict]:
    db_path = resolve_database_path(database_path)
    initialize_database(db_path)
    with connect_database(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, chat_id, chat_name, content, status, error,
                   bot_key, conversation_chat_id, external_chat_id, metadata_json
            FROM manual_reply_commands
            ORDER BY created_at ASC
            LIMIT ? OFFSET ?
            """,
            (limit, offset),
        ).fetchall()
    return [_row_to_command(row) for row in rows]


def get_manual_reply(
    command_id: str,
    database_path: Path | None = None,
) -> dict:
    db_path = resolve_database_path(database_path)
    initialize_database(db_path)
    with connect_database(db_path) as conn:
        row = conn.execute(
            """
            SELECT id, created_at, chat_id, chat_name, content, status, error,
                   bot_key, conversation_chat_id, external_chat_id, metadata_json
            FROM manual_reply_commands
            WHERE id = ?
            """,
            (command_id,),
        ).fetchone()
    return _row_to_command(row) if row else {}


def list_pending_manual_replies(
    database_path: Path | None = None,
    bot_key: str = "",
) -> list[dict]:
    db_path = resolve_database_path(database_path)
    initialize_database(db_path)
    with connect_database(db_path) as conn:
        rows = conn.execute(
            """
            SELECT id, created_at, chat_id, chat_name, content, status, error,
                   bot_key, conversation_chat_id, external_chat_id, metadata_json
            FROM manual_reply_commands
            WHERE status IN ('pending', 'processing')
              AND bot_key = ?
            ORDER BY created_at ASC
            """
            ,
            (bot_key,),
        ).fetchall()
    return [_row_to_command(row) for row in rows]


def mark_manual_reply(
    command_id: str,
    status: str,
    *,
    error: str = "",
    database_path: Path | None = None,
) -> None:
    db_path = resolve_database_path(database_path)
    initialize_database(db_path)
    with connect_database(db_path) as conn:
        conn.execute(
            """
            UPDATE manual_reply_commands
            SET status = ?, error = ?, updated_at = ?
            WHERE id = ?
            """,
            (status, error, utc_now(), command_id),
        )


def _row_to_command(row: Any) -> dict[str, Any]:
    item = dict(row)
    try:
        item["metadata"] = json.loads(str(item.pop("metadata_json") or "{}"))
    except json.JSONDecodeError:
        logger.warning(
            f"Failed to parse metadata_json: {item.get('metadata_json', '')!r}, "
            f"command_id={item.get('id', '')}"
        )
        item["metadata"] = {}
    return item
