from __future__ import annotations

from datetime import datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.db.core import connect_database, initialize_database
from app.log_categories import classify_log_category, normalize_log_category
from app.log_shape import normalize_project_log_shape
from app.utils import CST, utc_now


def insert_project_log(
    database_path: Path,
    *,
    level: str,
    source: str,
    message: str,
    detail: str = "",
    trace_id: str | None = None,
    error_code: str = "",
    category: str = "",
) -> str:
    # 过滤 DEBUG 级别日志
    level_upper = level.upper()
    if level_upper == "DEBUG":
        return ""
    initialize_database(database_path)
    current_trace_id = trace_id or str(uuid4())
    now = utc_now()
    normalized_message, normalized_detail = normalize_project_log_shape(
        source=source,
        message=message,
        detail=detail,
    )
    resolved_category = classify_log_category(
        source=source,
        message=normalized_message,
        detail=normalized_detail,
        category=category,
    )
    with connect_database(database_path) as conn:
        conn.execute(
            """
            INSERT INTO project_logs (
                id, trace_id, created_at, category, level, source, message, detail, error_code
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid4().hex,
                current_trace_id,
                now,
                resolved_category,
                level_upper,
                source,
                normalized_message,
                normalized_detail,
                error_code,
            ),
        )
    return current_trace_id


def insert_bot_process_log(
    database_path: Path,
    *,
    bot_key: str,
    content: str,
) -> str:
    initialize_database(database_path)
    current_trace_id = str(uuid4())
    now = utc_now()
    with connect_database(database_path) as conn:
        conn.execute(
            """
            INSERT INTO project_logs (
                id, trace_id, created_at, category, level, source, message, detail, error_code
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                uuid4().hex,
                current_trace_id,
                now,
                "bot",
                "INFO",
                f"bot_process.{bot_key}",
                "Bot process output",
                content,
                "",
            ),
        )
    return current_trace_id


def get_bot_process_logs(
    database_path: Path,
    *,
    bot_key: str,
    max_lines: int = 50,
) -> str:
    initialize_database(database_path)
    source_prefix = f"bot_process.{bot_key}"
    with connect_database(database_path) as conn:
        rows = conn.execute(
            """
            SELECT detail
            FROM project_logs
            WHERE source = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (source_prefix, max_lines),
        ).fetchall()
    
    logs = []
    for row in rows:
        logs.append(row["detail"])
    
    return "\n".join(reversed(logs)) if logs else ""


def list_project_logs(
    database_path: Path,
    *,
    category: str = "",
    level: str = "",
    trace_id: str = "",
    start_time: str = "",
    end_time: str = "",
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    initialize_database(database_path)
    clauses = []
    params: list[Any] = []
    normalized_start_time = _normalize_filter_datetime(start_time)
    normalized_end_time = _normalize_filter_datetime(end_time)

    normalized_category = normalize_log_category(category, default="")
    if normalized_category:
        clauses.append("category = ?")
        params.append(normalized_category)
    if level:
        clauses.append("level = ?")
        params.append(level.upper())
    if trace_id:
        clauses.append("trace_id LIKE ?")
        params.append(f"%{trace_id}%")
    if normalized_start_time:
        clauses.append("created_at >= ?")
        params.append(normalized_start_time)
    if normalized_end_time:
        clauses.append("created_at <= ?")
        params.append(normalized_end_time)

    where_sql = " AND ".join(clauses) if clauses else "1 = 1"

    current_page = max(1, page)
    current_page_size = max(1, min(page_size, 100))
    offset = (current_page - 1) * current_page_size

    with connect_database(database_path) as conn:
        count_sql = f"SELECT COUNT(*) AS total FROM project_logs WHERE {where_sql}"
        count_row = conn.execute(count_sql, params).fetchone()
        total = count_row["total"]

        total_pages = (total + current_page_size - 1) // current_page_size if total > 0 else 1

        sql = f"""
            SELECT id, trace_id, created_at, category, level, source, message, detail, error_code
            FROM project_logs
            WHERE {where_sql}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
        """
        rows = conn.execute(sql, params + [current_page_size, offset]).fetchall()

    return {
        "logs": [
            {
                **dict(row),
                "category": classify_log_category(
                    source=str(row["source"] or ""),
                    message=str(row["message"] or ""),
                    detail=str(row["detail"] or ""),
                    category=str(row["category"] or ""),
                ),
            }
            for row in rows
        ],
        "total": total,
        "page": current_page,
        "page_size": current_page_size,
        "total_pages": total_pages,
    }


def _normalize_filter_datetime(value: str) -> str:
    raw = str(value or "").strip()
    if not raw:
        return ""
    try:
        dt = datetime.fromisoformat(raw)
    except ValueError:
        return raw
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=CST)
    return dt.astimezone(CST).isoformat()
