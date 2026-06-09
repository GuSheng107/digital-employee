from __future__ import annotations

import asyncio
from pathlib import Path
from uuid import uuid4

from app.db.core import connect_database, initialize_database
from app.utils import utc_now, utc_now_minus_seconds


CHAT_COMPRESS_LOCK_MAX_AGE_SECONDS = 300


def acquire_llm_slot(
    database_path: Path,
    *,
    slot_type: str,
    trace_id: str = "",
    max_concurrent: int = 30,
) -> str | None:
    initialize_database(database_path)
    now = utc_now()
    slot_id = f"{slot_type}.{uuid4().hex[:12]}"
    with connect_database(database_path) as conn:
        cursor = conn.execute(
            """
            INSERT INTO llm_request_slots (slot_id, slot_type, trace_id, acquired_at)
            SELECT ?, ?, ?, ?
            WHERE (SELECT COUNT(*) FROM llm_request_slots WHERE slot_type = ?) < ?
            """,
            (slot_id, slot_type, trace_id, now, slot_type, max(1, int(max_concurrent))),
        )
        if cursor.rowcount > 0:
            return slot_id
    return None


def release_llm_slot(database_path: Path, *, slot_id: str) -> bool:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        cursor = conn.execute(
            "DELETE FROM llm_request_slots WHERE slot_id = ?",
            (slot_id,),
        )
        return cursor.rowcount > 0


def count_active_llm_slots(database_path: Path, *, slot_type: str = "") -> int:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        if slot_type:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM llm_request_slots WHERE slot_type = ?",
                (slot_type,),
            ).fetchone()
        else:
            row = conn.execute(
                "SELECT COUNT(*) AS cnt FROM llm_request_slots"
            ).fetchone()
    return int(row["cnt"]) if row else 0


def release_slots_by_trace_id(database_path: Path, *, trace_id: str) -> int:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        cursor = conn.execute(
            "DELETE FROM llm_request_slots WHERE trace_id = ?",
            (trace_id,),
        )
        return cursor.rowcount


def cleanup_stale_llm_slots(database_path: Path, *, max_age_minutes: int = 30) -> int:
    initialize_database(database_path)
    cutoff = utc_now_minus_seconds(max_age_minutes * 60)
    with connect_database(database_path) as conn:
        cursor = conn.execute(
            "DELETE FROM llm_request_slots WHERE acquired_at != '' AND acquired_at < ?",
            (cutoff,),
        )
        return cursor.rowcount


def reset_all_llm_slots(database_path: Path) -> int:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        cursor = conn.execute("DELETE FROM llm_request_slots")
        return cursor.rowcount


def acquire_chat_compress_lock(
    database_path: Path,
    *,
    chat_id: str,
    trace_id: str = "",
    max_age_seconds: int = CHAT_COMPRESS_LOCK_MAX_AGE_SECONDS,
) -> str | None:
    initialize_database(database_path)
    now = utc_now()
    cutoff = utc_now_minus_seconds(max_age_seconds)
    slot_type = f"compress.{chat_id}"
    with connect_database(database_path) as conn:
        conn.execute(
            "DELETE FROM llm_request_slots WHERE slot_type = ? AND acquired_at < ?",
            (slot_type, cutoff),
        )
        slot_id = f"compress.{uuid4().hex[:12]}"
        cursor = conn.execute(
            """
            INSERT INTO llm_request_slots (slot_id, slot_type, trace_id, acquired_at)
            SELECT ?, ?, ?, ?
            WHERE (SELECT COUNT(*) FROM llm_request_slots WHERE slot_type = ?) = 0
            """,
            (slot_id, slot_type, trace_id, now, slot_type),
        )
        if cursor.rowcount > 0:
            return slot_id
    return None


def release_chat_compress_lock(database_path: Path, *, slot_id: str) -> bool:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        cursor = conn.execute(
            "DELETE FROM llm_request_slots WHERE slot_id = ? AND slot_type LIKE 'compress.%'",
            (slot_id,),
        )
        return cursor.rowcount > 0


def is_chat_locked(database_path: Path, *, chat_id: str) -> bool:
    initialize_database(database_path)
    slot_type = f"compress.{chat_id}"
    now = utc_now()
    cutoff = utc_now_minus_seconds(CHAT_COMPRESS_LOCK_MAX_AGE_SECONDS)
    with connect_database(database_path) as conn:
        row = conn.execute(
            """
            SELECT COUNT(*) AS cnt FROM llm_request_slots
            WHERE slot_type = ? AND acquired_at >= ?
            """,
            (slot_type, cutoff),
        ).fetchone()
    return (int(row["cnt"]) if row else 0) > 0


async def wait_for_chat_compress_unlock(
    database_path: Path,
    *,
    chat_id: str,
    timeout_seconds: int = CHAT_COMPRESS_LOCK_MAX_AGE_SECONDS,
    poll_interval_seconds: float = 0.5,
) -> bool:
    if not str(chat_id or "").strip():
        return True
    deadline = asyncio.get_running_loop().time() + max(0.1, float(timeout_seconds))
    while is_chat_locked(database_path, chat_id=chat_id):
        if asyncio.get_running_loop().time() >= deadline:
            return False
        await asyncio.sleep(max(0.1, float(poll_interval_seconds)))
    return True
