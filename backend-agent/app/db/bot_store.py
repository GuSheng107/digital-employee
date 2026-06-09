from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.crypto_utils import get_crypto_utils
from app.db.core import (
    connect_database,
    initialize_database,
)
from app.db.schema import _clean_identifier
from app.db.user_store import upsert_user_display_name
from app.exceptions import CryptoError
from app.utils import utc_now


def make_conversation_key(
    bot_key: str,
    external_chat_id: str,
    *,
    kind: str = "external",
) -> str:
    clean_bot = _clean_identifier(bot_key)
    clean_external = str(external_chat_id or "unknown").strip() or "unknown"
    if kind == "toolbox":
        return f"toolbox:{clean_bot}:{clean_external}"
    return f"{kind}:{clean_bot}:{clean_external}"


def list_bot_configs(database_path: Path) -> list[dict[str, Any]]:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM bot_config
            ORDER BY created_at ASC
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_bot_configs_paginated(
    database_path: Path, page: int = 1, page_size: int = 10, keyword: str = "",
    include_deleted: bool = False,
) -> dict[str, Any]:
    initialize_database(database_path)
    current_page = max(1, int(page or 1))
    current_page_size = min(max(1, int(page_size or 10)), 100)
    search_keyword = str(keyword or "").strip()
    clauses = []
    params = []
    if search_keyword:
        clauses.append("name LIKE ?")
        params.append(f"%{search_keyword}%")
    if not include_deleted:
        clauses.append("deleted_at = ''")
    where_sql = " AND ".join(clauses) if clauses else "1 = 1"

    with connect_database(database_path) as conn:
        count_row = conn.execute(
            f"SELECT COUNT(*) as total FROM bot_config WHERE {where_sql}",
            params,
        ).fetchone()
        total = count_row["total"]

        offset = (current_page - 1) * current_page_size
        rows = conn.execute(
            f"""
            SELECT *
            FROM bot_config
            WHERE {where_sql}
            ORDER BY created_at ASC
            LIMIT ? OFFSET ?
            """,
            params + [current_page_size, offset],
        ).fetchall()

        total_pages = (total + current_page_size - 1) // current_page_size if total > 0 else 1
        return {
            "bots": [dict(row) for row in rows],
            "total": total,
            "page": current_page,
            "page_size": current_page_size,
            "total_pages": total_pages,
        }


def toggle_bot_active(database_path: Path, bot_key: str, is_active: bool) -> None:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        if is_active:
            row = conn.execute(
                "SELECT bound_chat_id FROM bot_config WHERE bot_key = ?",
                (bot_key,),
            ).fetchone()
            if row is None:
                raise ValueError("未找到对应的 Bot。")
            if not str(row["bound_chat_id"] or "").strip():
                raise ValueError("Bot 必须先绑定后才能启用。")
        conn.execute(
            """
            UPDATE bot_config
            SET is_active = ?, updated_at = ?
            WHERE bot_key = ?
            """,
            (int(bool(is_active)), now, bot_key),
        )


def batch_delete_bots(database_path: Path, bot_keys: list[str]) -> int:
    initialize_database(database_path)
    deleted_count = 0
    now = utc_now()
    with connect_database(database_path) as conn:
        for bot_key in bot_keys:
            cursor = conn.execute(
                """
                UPDATE bot_config
                SET deleted_at = ?, is_active = 0, agent_provider = '', updated_at = ?
                WHERE bot_key = ? AND deleted_at = ''
                """,
                (now, now, bot_key),
            )
            deleted_count += cursor.rowcount
            conn.execute("DELETE FROM bot_skill_mapping WHERE bot_key = ?", (bot_key,))
            conn.execute("DELETE FROM bot_mcp_mapping WHERE bot_key = ?", (bot_key,))
            conn.execute(
                """
                UPDATE conversations
                SET conversation_status = 'archived', unread_count = 0, updated_at = ?
                WHERE bot_key = ?
                """,
                (now, bot_key),
            )
    return deleted_count


def restore_bots(database_path: Path, bot_keys: list[str]) -> int:
    initialize_database(database_path)
    now = utc_now()
    restored_count = 0
    with connect_database(database_path) as conn:
        for bot_key in bot_keys:
            cursor = conn.execute(
                """
                UPDATE bot_config
                SET deleted_at = '', updated_at = ?
                WHERE bot_key = ? AND deleted_at != ''
                """,
                (now, bot_key),
            )
            restored_count += cursor.rowcount
    return restored_count


def list_bots_by_keys(database_path: Path, bot_keys: list[str]) -> list[dict[str, Any]]:
    initialize_database(database_path)
    clean_keys = [str(item) for item in bot_keys if str(item)]
    if not clean_keys:
        return []
    placeholders = ", ".join("?" for _ in clean_keys)
    with connect_database(database_path) as conn:
        rows = conn.execute(
            f"SELECT * FROM bot_config WHERE bot_key IN ({placeholders})",
            clean_keys,
        ).fetchall()
    return [dict(row) for row in rows]


def get_bot_config(database_path: Path, bot_key: str) -> dict[str, Any] | None:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        row = conn.execute(
            "SELECT * FROM bot_config WHERE bot_key = ?",
            (bot_key,),
        ).fetchone()
    if row is None:
        return None
    return dict(row)


def _validate_bot_name_unique(
    conn: Any,
    name: str,
    *,
    exclude_bot_key: str | None = None,
) -> None:
    row = conn.execute(
        """
        SELECT bot_key
        FROM bot_config
        WHERE name = ? AND deleted_at = '' AND (? IS NULL OR bot_key <> ?)
        LIMIT 1
        """,
        (name, exclude_bot_key, exclude_bot_key),
    ).fetchone()
    if row is not None:
        raise ValueError("Bot 名称必须唯一。")


def upsert_bot_config(database_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    initialize_database(database_path)
    crypto = get_crypto_utils()
    now = utc_now()
    bot_key = _clean_identifier(str(payload.get("bot_key") or "")) or uuid4().hex
    with connect_database(database_path) as conn:
        existing = conn.execute(
            "SELECT * FROM bot_config WHERE bot_key = ?",
            (bot_key,),
        ).fetchone()
        fields = _resolve_bot_fields(payload, existing, crypto)
        _validate_bot_name_unique(conn, fields["name"], exclude_bot_key=bot_key)
        try:
            conn.execute(
                """
                INSERT INTO bot_config (
                    bot_key, name, bot_id, secret,
                    bind_status,
                    bound_user_id, bound_chat_id, agent_provider,
                    system_prompt, startup_text, shutdown_text,
                    is_active,
                    created_at, updated_at, deleted_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, '')
                ON CONFLICT(bot_key) DO UPDATE SET
                    name = excluded.name,
                    bot_id = excluded.bot_id,
                    secret = excluded.secret,
                    bind_status = excluded.bind_status,
                    agent_provider = excluded.agent_provider,
                    system_prompt = excluded.system_prompt,
                    startup_text = excluded.startup_text,
                    shutdown_text = excluded.shutdown_text,
                    is_active = excluded.is_active,
                    updated_at = excluded.updated_at
                """,
                (
                    bot_key,
                    fields["name"],
                    fields["bot_id"],
                    fields["secret_encrypted"],
                    fields["bind_status"],
                    fields["bound_user_id"],
                    fields["bound_chat_id"],
                    fields["agent_provider"],
                    fields["system_prompt"],
                    fields["startup_text"],
                    fields["shutdown_text"],
                    fields["is_active"],
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            if "bot_config.name" in str(exc) or "idx_bot_config_unique_active_name" in str(exc):
                raise ValueError("Bot 名称必须唯一。") from exc
            raise
    bot = get_bot_config(database_path, bot_key)
    if bot is None:
        raise RuntimeError("Failed to save bot config.")
    return bot


def _resolve_bot_fields(
    payload: dict[str, Any],
    existing: Any,
    crypto: Any,
) -> dict[str, Any]:
    bot_name = str(payload.get("name")).strip()
    if not bot_name:
        raise ValueError("Bot 名称不能为空")
    bot_id = str(payload.get("bot_id") or (existing["bot_id"] if existing else "")).strip()
    if not bot_id:
        raise ValueError("Bot ID 不能为空")
    bind_status = str(payload.get("bind_status") or (existing["bind_status"] if existing else "unbound"))
    secret_plain = _resolve_secret(payload, existing, crypto)
    if "agent_provider" in payload:
        val = payload["agent_provider"]
        agent_provider = str(val).strip() if (val is not None and str(val).strip().lower() != "none") else ""
    else:
        agent_provider = str(existing["agent_provider"] if existing else "")
    return {
        "name": bot_name,
        "bot_id": bot_id,
        "secret_encrypted": crypto.encrypt(secret_plain),
        "bind_status": bind_status,
        "bound_user_id": str(existing["bound_user_id"] if existing else ""),
        "bound_chat_id": str(existing["bound_chat_id"] if existing else ""),
        "agent_provider": agent_provider,
        "system_prompt": str(payload.get("system_prompt") or (existing["system_prompt"] if existing else "")),
        "startup_text": str(payload.get("startup_text") or (existing["startup_text"] if existing else "")),
        "shutdown_text": str(payload.get("shutdown_text") or (existing["shutdown_text"] if existing else "")),
        "is_active": int(bool(payload.get("is_active", existing["is_active"] if existing else 0))),
    }


def _resolve_secret(
    payload: dict[str, Any],
    existing: Any,
    crypto: Any,
) -> str:
    existing_secret_plain = _decrypt_bot_secret(str(existing["secret"])) if existing else ""
    secret_value = payload.get("secret")
    if secret_value is None:
        secret_plain = existing_secret_plain
    else:
        secret_plain = str(secret_value)
        if not secret_plain and existing_secret_plain:
            secret_plain = existing_secret_plain
    if not secret_plain:
        raise ValueError("Secret 不能为空")
    return secret_plain


def mark_bot_rebinding(database_path: Path, bot_key: str) -> None:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        bot = conn.execute(
            "SELECT bound_chat_id FROM bot_config WHERE bot_key = ?",
            (bot_key,),
        ).fetchone()
        bound_chat_id = str(bot["bound_chat_id"] or "").strip() if bot else ""
        me_chat_id = make_conversation_key(bot_key, bound_chat_id, kind="me") if bound_chat_id else ""
        conn.execute(
            """
            UPDATE bot_config
            SET bind_status = 'binding',
                bound_user_id = '',
                bound_chat_id = '',
                updated_at = ?
            WHERE bot_key = ?
            """,
            (now, bot_key),
        )
        if me_chat_id:
            conn.execute("DELETE FROM chat_messages WHERE chat_id = ?", (me_chat_id,))
            conn.execute(
                "DELETE FROM conversation_context_summaries WHERE chat_id = ?",
                (me_chat_id,),
            )
            conn.execute("DELETE FROM conversations WHERE chat_id = ?", (me_chat_id,))


def unbind_bot(database_path: Path, bot_key: str) -> None:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        bot = conn.execute(
            "SELECT bound_chat_id FROM bot_config WHERE bot_key = ?",
            (bot_key,),
        ).fetchone()
        bound_chat_id = str(bot["bound_chat_id"] or "").strip() if bot else ""
        me_chat_id = make_conversation_key(bot_key, bound_chat_id, kind="me") if bound_chat_id else ""
        conn.execute(
            """
            UPDATE bot_config
            SET bind_status = 'unbound',
                bound_user_id = '',
                bound_chat_id = '',
                is_active = 0,
                updated_at = ?
            WHERE bot_key = ?
            """,
            (now, bot_key),
        )
        if me_chat_id:
            conn.execute("DELETE FROM chat_messages WHERE chat_id = ?", (me_chat_id,))
            conn.execute(
                "DELETE FROM conversation_context_summaries WHERE chat_id = ?",
                (me_chat_id,),
            )
            conn.execute("DELETE FROM conversations WHERE chat_id = ?", (me_chat_id,))


def complete_bot_binding(
    database_path: Path,
    *,
    bot_key: str,
    bound_user_id: str,
    bound_chat_id: str,
) -> dict[str, Any]:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        bot = conn.execute(
            "SELECT * FROM bot_config WHERE bot_key = ?",
            (bot_key,),
        ).fetchone()
        if bot is None:
            raise RuntimeError(f"Unknown bot: {bot_key}")
        conn.execute(
            """
            UPDATE bot_config
            SET bind_status = 'bound',
                bound_user_id = ?,
                bound_chat_id = ?,
                updated_at = ?
            WHERE bot_key = ?
            """,
            (bound_user_id, bound_chat_id, now, bot_key),
        )
        conversation_key = make_conversation_key(bot_key, bound_chat_id, kind="me")
        conn.execute(
            """
            INSERT INTO conversations (
                chat_id, chat_name, display_name, chat_type, sender_id, sender_name,
                last_message_at, bot_key, external_chat_id, conversation_kind,
                pinned, pin_rank, unread_count, last_context_compressed_at,
                reply_mode, conversation_status, created_at, updated_at, deleted_at
            )
            VALUES (?, ?, ?, 'single', ?, '我', ?, ?, ?, 'me', 1, 1000000000, 0, '', 'manual', 'active', ?, ?, '')
            ON CONFLICT(chat_id) DO UPDATE SET
                chat_name = excluded.chat_name,
                display_name = excluded.display_name,
                sender_id = excluded.sender_id,
                sender_name = excluded.sender_name,
                last_message_at = excluded.last_message_at,
                bot_key = excluded.bot_key,
                external_chat_id = excluded.external_chat_id,
                conversation_kind = 'me',
                pinned = 1,
                pin_rank = 1000000000,
                reply_mode = COALESCE(NULLIF(conversations.reply_mode, ''), 'manual'),
                deleted_at = '',
                updated_at = excluded.updated_at
            """,
            (
                conversation_key,
                f"我--{bot['name']}",
                f"我--{bot['name']}",
                bound_user_id,
                now,
                bot_key,
                bound_chat_id,
                now,
                now,
            ),
        )
        conn.execute(
            """
            DELETE FROM chat_messages
            WHERE external_chat_id = ? AND bot_key = ? AND chat_id != ?
            """,
            (bound_chat_id, bot_key, conversation_key),
        )
        conn.execute(
            """
            DELETE FROM conversations
            WHERE external_chat_id = ? AND bot_key = ? AND chat_id != ?
            """,
            (bound_chat_id, bot_key, conversation_key),
        )
    bot = get_bot_config(database_path, bot_key)
    if bot is None:
        raise RuntimeError("Failed to bind bot.")
    if str(bound_user_id or "").strip():
        upsert_user_display_name(
            database_path,
            user_id=str(bound_user_id).strip(),
            display_name="我",
        )
    return bot


def get_bot_runtime_settings(database_path: Path, *, bot_key: str = "") -> Any:
    from app.db.settings_store import load_settings_from_database
    return load_settings_from_database(database_path, bot_key=bot_key)


def _decrypt_bot_secret(secret: str) -> str:
    if not secret:
        return ""
    try:
        return get_crypto_utils().decrypt(secret)
    except CryptoError:
        raise


def _bot_dict_from_row(row: Any) -> dict[str, Any]:
    bot = dict(row)
    bot["secret"] = _decrypt_bot_secret(str(bot.get("secret", "")))
    return bot
