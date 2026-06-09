from __future__ import annotations

from pathlib import Path
from typing import Any

from app.db.core import connect_database, initialize_database
from app.utils import utc_now, utc_now_minus_seconds

RECENT_AI_WORK_KEEP_SECONDS = 15
AI_WORK_DELETABLE_STATUSES = ("completed", "failed", "busy", "cancelled", "cancel_requested")


def _quote_identifier(identifier: str) -> str:
    if not identifier or any(not (char.isalnum() or char == "_") for char in identifier):
        raise ValueError(f"Unsafe SQL identifier: {identifier!r}")
    return f'"{identifier}"'


def _ai_work_primary_key_column(conn: Any) -> str:
    rows = conn.execute("PRAGMA table_info(ai_work_items)").fetchall()
    pk_columns = sorted(
        (int(row[5] or 0), str(row[1]))
        for row in rows
        if int(row[5] or 0) > 0
    )
    if pk_columns:
        return pk_columns[0][1]
    columns = {str(row[1]) for row in rows}
    if "task_id" in columns:
        return "task_id"
    return "trace_id"


def _ai_work_task_dict(row: Any) -> dict[str, Any]:
    is_draft = bool(row["is_draft"])
    return {
        "task_id": str(row["task_id"]),
        "trace_id": str(row["trace_id"] or ""),
        "task_key": "ai_draft" if is_draft else "smart_reply",
        "task_name": "AI\u8349\u7a3f" if is_draft else "\u667a\u80fd\u56de\u590d",
        "task_scope": "system",
        "task_type": "one_time",
        "executor_kind": "bot",
        "executor_id": "",
        "description": "\u56de\u7b54\u7528\u6237\u95ee\u9898",
        "status": str(row["status"]),
        "chat_id": str(row["chat_id"]),
        "chat_name": str(row["chat_name"]),
        "prompt_text": str(row["question"]),
        "result_text": str(row["answer"]),
        "error": str(row["error"]),
        "stage": str(row["stage"]),
        "started_at": str(row["started_at"]),
        "created_at": str(row["started_at"]),
        "updated_at": str(row["updated_at"]),
        "finished_at": str(row["finished_at"]),
    }


def create_ai_work_item(
    database_path: Path,
    *,
    trace_id: str,
    chat_id: str,
    chat_name: str,
    question: str,
    stage: str = "接收消息",
) -> None:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        conn.execute(
            """
            INSERT INTO ai_work_items (
                trace_id, status, chat_id, chat_name, question,
                answer, error, stage, cancel_requested, started_at, updated_at, finished_at
            )
            VALUES (?, 'running', ?, ?, ?, '', '', ?, 0, ?, ?, '')
            ON CONFLICT(trace_id) DO UPDATE SET
                status = 'running',
                chat_id = excluded.chat_id,
                chat_name = excluded.chat_name,
                question = excluded.question,
                error = '',
                stage = excluded.stage,
                cancel_requested = 0,
                started_at = excluded.started_at,
                updated_at = excluded.updated_at,
                finished_at = ''
            """,
            (trace_id, chat_id, chat_name, question[:1000], stage, now, now),
        )


def update_ai_work_item(
    database_path: Path,
    *,
    trace_id: str,
    status: str,
    answer: str | None = None,
    error: str | None = None,
    stage: str = "",
) -> None:
    initialize_database(database_path)
    now = utc_now()
    finished_at = now if status in {"completed", "failed", "busy", "cancelled"} else ""
    with connect_database(database_path) as conn:
        conn.execute(
            """
            UPDATE ai_work_items
            SET status = ?,
                answer = CASE WHEN ? IS NOT NULL THEN ? ELSE answer END,
                error = CASE WHEN ? IS NOT NULL THEN ? ELSE error END,
                stage = CASE WHEN ? != '' THEN ? ELSE stage END,
                updated_at = ?,
                finished_at = CASE WHEN ? != '' THEN ? ELSE finished_at END
            WHERE trace_id = ?
              AND cancel_requested = 0
            """,
            (
                status,
                answer,
                str(answer or "")[:8000] if answer is not None else "",
                error,
                str(error or "")[:4000] if error is not None else "",
                stage,
                stage,
                now,
                finished_at,
                finished_at,
                trace_id,
            ),
        )


def get_ai_work_status(database_path: Path) -> dict[str, Any]:
    initialize_database(database_path)
    recent_cutoff = utc_now_minus_seconds(RECENT_AI_WORK_KEEP_SECONDS)
    _active_sql = """
        SELECT aw.trace_id, aw.status, aw.chat_id, aw.chat_name, aw.question, aw.answer,
               aw.error, aw.stage, aw.cancel_requested, aw.updated_at, aw.started_at,
               COALESCE(NULLIF(c.display_name, ''), c.chat_name, '') AS conv_display_name,
               COALESCE(c.chat_type, '') AS conv_chat_type,
               COALESCE(NULLIF(up.display_name, ''), NULLIF(c.sender_name, ''), '') AS conv_sender_name,
               (
                   SELECT pl.detail
                   FROM project_logs pl
                   WHERE pl.trace_id = aw.trace_id
                     AND pl.source = 'agent.reasoning'
                   ORDER BY pl.created_at DESC
                   LIMIT 1
               ) AS reasoning_detail
        FROM ai_work_items aw
        LEFT JOIN conversations c ON c.chat_id = aw.chat_id
        LEFT JOIN user_profile up ON up.user_id = c.sender_id
        WHERE aw.status IN ('queued', 'running', 'cancel_requested')
        ORDER BY aw.updated_at DESC
        LIMIT 20
    """
    _recent_sql = """
        SELECT aw.trace_id, aw.status, aw.chat_id, aw.chat_name, aw.question, aw.answer,
               aw.error, aw.stage, aw.cancel_requested, aw.started_at, aw.updated_at, aw.finished_at,
               COALESCE(NULLIF(c.display_name, ''), c.chat_name, '') AS conv_display_name,
               COALESCE(c.chat_type, '') AS conv_chat_type,
               COALESCE(NULLIF(up.display_name, ''), NULLIF(c.sender_name, ''), '') AS conv_sender_name,
               (
                   SELECT pl.detail
                   FROM project_logs pl
                   WHERE pl.trace_id = aw.trace_id
                     AND pl.source = 'agent.reasoning'
                   ORDER BY pl.created_at DESC
                   LIMIT 1
               ) AS reasoning_detail
        FROM ai_work_items aw
        LEFT JOIN conversations c ON c.chat_id = aw.chat_id
        LEFT JOIN user_profile up ON up.user_id = c.sender_id
        WHERE aw.status IN ('completed', 'failed', 'busy', 'cancelled')
          AND COALESCE(NULLIF(aw.finished_at, ''), aw.updated_at) >= ?
        ORDER BY aw.updated_at DESC
        LIMIT 10
    """
    with connect_database(database_path) as conn:
        active = [_ai_work_dict(row) for row in conn.execute(_active_sql).fetchall()]
        recent = [_ai_work_dict(row) for row in conn.execute(_recent_sql, (recent_cutoff,)).fetchall()]

    return {
        "busy": bool(active),
        "active": active,
        "recent": recent,
    }


def _ai_work_dict(row: Any) -> dict[str, Any]:
    item = dict(row)
    item["reasoning"] = _extract_reasoning_text(str(item.pop("reasoning_detail", "") or ""))
    return item


def _extract_reasoning_text(detail: str) -> str:
    if not detail:
        return ""
    marker = "【Agent think】"
    marker_index = detail.find(marker)
    if marker_index >= 0:
        text = detail[marker_index + len(marker):]
        text = text.lstrip("=\r\n\t ")
    else:
        text = detail
    return text.strip()[:8000]


def cancel_ai_work_item(database_path: Path, trace_id: str) -> bool:
    if not trace_id:
        return False
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        cursor = conn.execute(
            """
            UPDATE ai_work_items
            SET cancel_requested = 1,
                answer = CASE
                    WHEN status IN ('running', 'queued', 'cancel_requested') THEN ''
                    ELSE answer
                END,
                status = CASE
                    WHEN status IN ('running', 'queued', 'cancel_requested') THEN 'cancelled'
                    ELSE status
                END,
                stage = CASE
                    WHEN status IN ('running', 'queued', 'cancel_requested') THEN '已截断'
                    ELSE stage
                END,
                finished_at = CASE
                    WHEN status IN ('running', 'queued', 'cancel_requested') THEN ?
                    ELSE finished_at
                END,
                updated_at = ?
            WHERE trace_id = ?
            """,
            (now, now, trace_id),
        )
    return bool(cursor.rowcount)


def clear_ai_work_item(database_path: Path, trace_id: str) -> bool:
    if not trace_id:
        return False
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        cursor = conn.execute(
            """
            DELETE FROM ai_work_items
            WHERE trace_id = ?
              AND status IN ('completed', 'failed', 'busy', 'cancelled', 'cancel_requested')
            """,
            (trace_id,),
        )
    return bool(cursor.rowcount)


def get_ai_work_task_by_id(database_path: Path, item_id: str) -> dict[str, Any] | None:
    if not item_id:
        return None
    initialize_database(database_path)
    draft_stage = "\u6309\u94ae\u89e6\u53d1\u751f\u6210\u56de\u590d"
    with connect_database(database_path) as conn:
        pk_column = _ai_work_primary_key_column(conn)
        pk_sql = _quote_identifier(pk_column)
        row = conn.execute(
            f"""
            SELECT
                aw.{pk_sql} AS task_id,
                aw.trace_id,
                aw.status,
                aw.chat_id,
                aw.chat_name,
                aw.question,
                aw.answer,
                aw.error,
                aw.stage,
                aw.started_at,
                aw.updated_at,
                aw.finished_at,
                CASE
                    WHEN aw.stage = ?
                      OR EXISTS (
                          SELECT 1
                          FROM token_usage tu
                          WHERE tu.trace_id = aw.trace_id
                            AND tu.call_type = 'draft'
                          LIMIT 1
                      )
                    THEN 1
                    ELSE 0
                END AS is_draft
            FROM ai_work_items aw
            WHERE aw.{pk_sql} = ?
            """,
            (draft_stage, item_id),
        ).fetchone()
    if row is None:
        return None
    return _ai_work_task_dict(row)


def clear_ai_work_item_by_id(database_path: Path, item_id: str) -> bool:
    if not item_id:
        return False
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        pk_column = _ai_work_primary_key_column(conn)
        pk_sql = _quote_identifier(pk_column)
        placeholders = ",".join("?" for _ in AI_WORK_DELETABLE_STATUSES)
        cursor = conn.execute(
            f"""
            DELETE FROM ai_work_items
            WHERE {pk_sql} = ?
              AND status IN ({placeholders})
            """,
            (item_id, *AI_WORK_DELETABLE_STATUSES),
        )
    return bool(cursor.rowcount)


def is_ai_work_cancel_requested(database_path: Path, trace_id: str) -> bool:
    if not trace_id:
        return False
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        row = conn.execute(
            "SELECT cancel_requested FROM ai_work_items WHERE trace_id = ?",
            (trace_id,),
        ).fetchone()
    return bool(row and row["cancel_requested"])
