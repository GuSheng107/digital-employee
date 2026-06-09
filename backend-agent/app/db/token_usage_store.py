from __future__ import annotations

import uuid
from datetime import datetime, timedelta
from pathlib import Path
from typing import Any

from app.db.core import connect_database, initialize_database
from app.utils import CST, utc_now


def record_token_usage(
    database_path: Path,
    *,
    provider_key: str = "",
    provider_type: str = "",
    model: str = "",
    call_type: str = "answer",
    chat_id: str = "",
    bot_key: str = "",
    trace_id: str = "",
    input_tokens: int = 0,
    output_tokens: int = 0,
    total_tokens: int = 0,
) -> None:
    if total_tokens <= 0 and input_tokens <= 0 and output_tokens <= 0:
        return
    initialize_database(database_path)
    now = utc_now()
    record_id = uuid.uuid4().hex
    with connect_database(database_path) as conn:
        conn.execute(
            """
            INSERT INTO token_usage (
                id, created_at, provider_key, provider_type, model,
                call_type, chat_id, bot_key, trace_id,
                input_tokens, output_tokens, total_tokens
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                record_id,
                now,
                provider_key,
                provider_type,
                model,
                call_type,
                chat_id,
                bot_key,
                trace_id,
                input_tokens,
                output_tokens,
                total_tokens or (input_tokens + output_tokens),
            ),
        )


def get_latest_token_usage(
    database_path: Path,
    *,
    trace_id: str,
) -> dict[str, Any]:
    if not trace_id:
        return {}
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        row = conn.execute(
            """
            SELECT created_at, provider_key, provider_type, model, call_type, chat_id, bot_key, trace_id,
                   input_tokens, output_tokens, total_tokens
            FROM token_usage
            WHERE trace_id = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (trace_id,),
        ).fetchone()
    return dict(row) if row else {}


def get_token_usage_summary(database_path: Path) -> dict[str, Any]:
    initialize_database(database_path)
    now = datetime.now(CST)
    week_start = now - timedelta(days=6)
    month_start = now - timedelta(days=29)
    week_start_iso = week_start.isoformat()
    month_start_iso = month_start.isoformat()
    today_iso = now.isoformat()
    today_label = now.date().isoformat()
    week_label = f"{week_start.date().isoformat()} ~ {today_label}"
    month_label = f"{month_start.date().isoformat()} ~ {today_label}"
    bot_call_types = ("answer", "draft", "chat", "bot_task")
    with connect_database(database_path) as conn:
        total_row = conn.execute(
            "SELECT COALESCE(SUM(total_tokens), 0) AS total FROM token_usage"
        ).fetchone()
        total_range_row = conn.execute(
            """
            SELECT MIN(DATE(created_at)) AS start_date, MAX(DATE(created_at)) AS end_date
            FROM token_usage
            """
        ).fetchone()
        bot_row = conn.execute(
            """
            SELECT COALESCE(SUM(total_tokens), 0) AS total
            FROM token_usage
            WHERE call_type IN (?, ?, ?, ?)
            """,
            bot_call_types,
        ).fetchone()
        system_row = conn.execute(
            """
            SELECT COALESCE(SUM(total_tokens), 0) AS total
            FROM token_usage
            WHERE call_type NOT IN (?, ?, ?, ?)
            """,
            bot_call_types,
        ).fetchone()
        input_row = conn.execute(
            "SELECT COALESCE(SUM(input_tokens), 0) AS total FROM token_usage"
        ).fetchone()
        output_row = conn.execute(
            "SELECT COALESCE(SUM(output_tokens), 0) AS total FROM token_usage"
        ).fetchone()
        weekly_total_row = conn.execute(
            "SELECT COALESCE(SUM(total_tokens), 0) AS total FROM token_usage WHERE created_at >= ? AND created_at <= ?",
            (week_start_iso, today_iso),
        ).fetchone()
        monthly_total_row = conn.execute(
            "SELECT COALESCE(SUM(total_tokens), 0) AS total FROM token_usage WHERE created_at >= ? AND created_at <= ?",
            (month_start_iso, today_iso),
        ).fetchone()
        record_count_row = conn.execute(
            "SELECT COUNT(*) AS count FROM token_usage"
        ).fetchone()
        token_record_stats_row = conn.execute(
            """
            SELECT
                CAST(ROUND(COALESCE(AVG(total_tokens), 0)) AS INTEGER) AS avg_total,
                COALESCE(MAX(total_tokens), 0) AS max_total
            FROM token_usage
            """
        ).fetchone()
        request_count_row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM (
                SELECT COALESCE(NULLIF(trace_id, ''), id) AS request_key
                FROM token_usage
                GROUP BY COALESCE(NULLIF(trace_id, ''), id)
            ) AS request_groups
            """
        ).fetchone()
        multi_call_request_row = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM (
                SELECT COALESCE(NULLIF(trace_id, ''), id) AS request_key
                FROM token_usage
                GROUP BY COALESCE(NULLIF(trace_id, ''), id)
                HAVING COUNT(*) > 1
            ) AS multi_call_request_groups
            """
        ).fetchone()

    total_start = total_range_row["start_date"] if total_range_row["start_date"] else today_label
    total_end = total_range_row["end_date"] if total_range_row["end_date"] else today_label
    total_label = f"{total_start} ~ {total_end}"

    return {
        "total_tokens": int(total_row["total"]),
        "bot_tokens": int(bot_row["total"]),
        "system_tokens": int(system_row["total"]),
        "input_tokens": int(input_row["total"]),
        "output_tokens": int(output_row["total"]),
        "weekly_tokens": int(weekly_total_row["total"]),
        "monthly_tokens": int(monthly_total_row["total"]),
        "record_count": int(record_count_row["count"]),
        "avg_tokens_per_record": int(token_record_stats_row["avg_total"]),
        "max_tokens_per_record": int(token_record_stats_row["max_total"]),
        "request_count": int(request_count_row["count"]),
        "multi_call_request_count": int(multi_call_request_row["count"]),
        "total_range_label": total_label,
        "weekly_range_label": week_label,
        "monthly_range_label": month_label,
    }


def get_token_usage_summary_by_bot(
    database_path: Path,
    *,
    bot_key: str = "",
    provider_key: str = "",
) -> dict[str, Any]:
    initialize_database(database_path)
    now = datetime.now(CST)
    today_start = now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()
    
    # 根据是否提供 bot_key 来构建不同的查询条件
    with connect_database(database_path) as conn:
        if bot_key:
            # 如果有 bot_key，优先按 bot_key 筛选
            today_row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(total_tokens), 0) AS today_tokens,
                    COALESCE(SUM(input_tokens), 0) AS today_input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS today_output_tokens
                FROM token_usage
                WHERE created_at >= ?
                  AND bot_key = ?
                """,
                (today_start, bot_key),
            ).fetchone()
            total_row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(input_tokens), 0) AS total_input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS total_output_tokens
                FROM token_usage
                WHERE bot_key = ?
                """,
                (bot_key,),
            ).fetchone()
        elif provider_key:
            # 如果没有 bot_key 但有 provider_key，按 provider_key 筛选
            today_row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(total_tokens), 0) AS today_tokens,
                    COALESCE(SUM(input_tokens), 0) AS today_input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS today_output_tokens
                FROM token_usage
                WHERE created_at >= ?
                  AND provider_key = ?
                """,
                (today_start, provider_key),
            ).fetchone()
            total_row = conn.execute(
                """
                SELECT
                    COALESCE(SUM(total_tokens), 0) AS total_tokens,
                    COALESCE(SUM(input_tokens), 0) AS total_input_tokens,
                    COALESCE(SUM(output_tokens), 0) AS total_output_tokens
                FROM token_usage
                WHERE provider_key = ?
                """,
                (provider_key,),
            ).fetchone()
        else:
            # 都没有的话返回 0
            today_row = {"today_tokens": 0, "today_input_tokens": 0, "today_output_tokens": 0}
            total_row = {"total_tokens": 0, "total_input_tokens": 0, "total_output_tokens": 0}
    
    return {
        "today_tokens": int(today_row["today_tokens"]),
        "today_input_tokens": int(today_row["today_input_tokens"]),
        "today_output_tokens": int(today_row["today_output_tokens"]),
        "total_tokens": int(total_row["total_tokens"]),
        "total_input_tokens": int(total_row["total_input_tokens"]),
        "total_output_tokens": int(total_row["total_output_tokens"]),
    }
