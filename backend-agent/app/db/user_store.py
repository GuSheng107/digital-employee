from __future__ import annotations

from pathlib import Path
from typing import Any

from app.db.core import connect_database, initialize_database
from app.utils import utc_now


def get_user_display_name(database_path: Path, user_id: str) -> dict[str, Any] | None:
    initialize_database(database_path)
    clean_user_id = str(user_id or "").strip()
    if not clean_user_id:
        return None
    with connect_database(database_path) as conn:
        row = conn.execute(
            """
            SELECT user_id, display_name, created_at, updated_at
            FROM user_profile
            WHERE user_id = ?
            """,
            (clean_user_id,),
        ).fetchone()
    return dict(row) if row else None


def list_user_display_names(database_path: Path, user_ids: list[str]) -> dict[str, str]:
    initialize_database(database_path)
    clean_ids = [str(item or "").strip() for item in user_ids if str(item or "").strip()]
    if not clean_ids:
        return {}
    placeholders = ", ".join("?" for _ in clean_ids)
    with connect_database(database_path) as conn:
        rows = conn.execute(
            f"""
            SELECT user_id, display_name
            FROM user_profile
            WHERE user_id IN ({placeholders})
            """,
            clean_ids,
        ).fetchall()
    return {
        str(row["user_id"]).strip(): str(row["display_name"] or "").strip()
        for row in rows
        if str(row["user_id"] or "").strip()
    }


def upsert_user_display_name(
    database_path: Path,
    *,
    user_id: str,
    display_name: str,
) -> dict[str, Any]:
    initialize_database(database_path)
    clean_user_id = str(user_id or "").strip()
    clean_display_name = str(display_name or "").strip()
    if not clean_user_id:
        raise ValueError("user_id 不能为空")
    if not clean_display_name:
        raise ValueError("用户显示名不能为空")
    now = utc_now()
    with connect_database(database_path) as conn:
        conn.execute(
            """
            INSERT INTO user_profile (user_id, display_name, created_at, updated_at)
            VALUES (?, ?, ?, ?)
            ON CONFLICT(user_id) DO UPDATE SET
                display_name = excluded.display_name,
                updated_at = excluded.updated_at
            """,
            (clean_user_id, clean_display_name, now, now),
        )
    profile = get_user_display_name(database_path, clean_user_id)
    if profile is None:
        raise RuntimeError("保存用户显示名失败")
    return profile


def sync_user_conversation_display_name(
    database_path: Path,
    *,
    user_id: str,
    display_name: str,
) -> None:
    initialize_database(database_path)
    clean_user_id = str(user_id or "").strip()
    if not clean_user_id:
        raise ValueError("user_id 不能为空")
    clean_display_name = str(display_name or "").strip()
    with connect_database(database_path) as conn:
        if not clean_display_name:
            raise ValueError("用户显示名不能为空")
        conn.execute(
            """
            UPDATE conversations
            SET chat_name = ?, display_name = ?, updated_at = ?
            WHERE sender_id = ?
              AND chat_type NOT IN ('group', 'room')
              AND conversation_kind != 'me'
            """,
            (clean_display_name, clean_display_name, utc_now(), clean_user_id),
        )


def update_user_display_name(
    database_path: Path,
    *,
    user_id: str,
    display_name: str,
) -> dict[str, Any] | None:
    initialize_database(database_path)
    clean_user_id = str(user_id or "").strip()
    clean_display_name = str(display_name or "").strip()
    if not clean_user_id:
        raise ValueError("user_id 不能为空")
    
    if not clean_display_name:
        raise ValueError("用户显示名不能为空")
    result = upsert_user_display_name(
        database_path,
        user_id=clean_user_id,
        display_name=clean_display_name,
    )
    sync_user_conversation_display_name(
        database_path,
        user_id=clean_user_id,
        display_name=clean_display_name,
    )
    return result
