from __future__ import annotations

import json
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.db.core import connect_database, initialize_database
from app.utils import utc_now, utc_now_minus_days


def _to_json(value: Any) -> str:
    try:
        return json.dumps(value or [], ensure_ascii=False)
    except TypeError:
        return "[]"


def _from_json_list(value: str) -> list[str]:
    try:
        data = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    if not isinstance(data, list):
        return []
    return [str(item) for item in data]


def upsert_memory_usage_audit(
    database_path: Path,
    *,
    trace_id: str,
    chat_id: str = "",
    bot_key: str = "",
    call_type: str = "",
    status: str = "",
    user_query: str = "",
    memory_pack: str = "",
    selected_files: list[str] | None = None,
    selected_sections: list[str] | None = None,
    omitted_files: list[str] | None = None,
    token_budget_used_estimate: int = 0,
    confidence: str = "",
    needs_more_memory: bool = False,
    reason: str = "",
    final_answer: str | None = None,
    input_tokens: int | None = None,
    output_tokens: int | None = None,
    total_tokens: int | None = None,
) -> None:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        existing = conn.execute(
            "SELECT id FROM memory_usage_audits WHERE trace_id = ? LIMIT 1",
            (trace_id,),
        ).fetchone()
        row_id = str(existing["id"]) if existing else uuid4().hex
        selected_files_json = _to_json(selected_files)
        selected_sections_json = _to_json(selected_sections)
        omitted_files_json = _to_json(omitted_files)
        payload = (
            chat_id,
            bot_key,
            call_type,
            status,
            user_query[:4000],
            memory_pack[:20000],
            selected_files_json,
            selected_sections_json,
            omitted_files_json,
            max(0, int(token_budget_used_estimate or 0)),
            str(confidence or "")[:32],
            1 if needs_more_memory else 0,
            str(reason or "")[:4000],
            str(final_answer or "")[:8000] if final_answer is not None else "",
            max(0, int(input_tokens or 0)) if input_tokens is not None else 0,
            max(0, int(output_tokens or 0)) if output_tokens is not None else 0,
            max(0, int(total_tokens or 0)) if total_tokens is not None else 0,
            now,
        )
        if existing:
            conn.execute(
                """
                UPDATE memory_usage_audits
                SET chat_id = CASE WHEN ? != '' THEN ? ELSE chat_id END,
                    bot_key = CASE WHEN ? != '' THEN ? ELSE bot_key END,
                    call_type = CASE WHEN ? != '' THEN ? ELSE call_type END,
                    status = CASE WHEN ? != '' THEN ? ELSE status END,
                    user_query = CASE WHEN ? != '' THEN ? ELSE user_query END,
                    memory_pack = CASE WHEN ? != '' THEN ? ELSE memory_pack END,
                    selected_files_json = CASE WHEN ? != '[]' THEN ? ELSE selected_files_json END,
                    selected_sections_json = CASE WHEN ? != '[]' THEN ? ELSE selected_sections_json END,
                    omitted_files_json = CASE WHEN ? != '[]' THEN ? ELSE omitted_files_json END,
                    token_budget_used_estimate = CASE WHEN ? > 0 THEN ? ELSE token_budget_used_estimate END,
                    confidence = CASE WHEN ? != '' THEN ? ELSE confidence END,
                    needs_more_memory = ?,
                    reason = CASE WHEN ? != '' THEN ? ELSE reason END,
                    final_answer = CASE WHEN ? != '' THEN ? ELSE final_answer END,
                    input_tokens = CASE WHEN ? > 0 THEN ? ELSE input_tokens END,
                    output_tokens = CASE WHEN ? > 0 THEN ? ELSE output_tokens END,
                    total_tokens = CASE WHEN ? > 0 THEN ? ELSE total_tokens END,
                    updated_at = ?
                WHERE trace_id = ?
                """,
                (
                    chat_id, chat_id,
                    bot_key, bot_key,
                    call_type, call_type,
                    status, status,
                    user_query[:4000], user_query[:4000],
                    memory_pack[:20000], memory_pack[:20000],
                    selected_files_json, selected_files_json,
                    selected_sections_json, selected_sections_json,
                    omitted_files_json, omitted_files_json,
                    max(0, int(token_budget_used_estimate or 0)), max(0, int(token_budget_used_estimate or 0)),
                    str(confidence or "")[:32], str(confidence or "")[:32],
                    1 if needs_more_memory else 0,
                    str(reason or "")[:4000], str(reason or "")[:4000],
                    str(final_answer or "")[:8000] if final_answer is not None else "", str(final_answer or "")[:8000] if final_answer is not None else "",
                    max(0, int(input_tokens or 0)) if input_tokens is not None else 0, max(0, int(input_tokens or 0)) if input_tokens is not None else 0,
                    max(0, int(output_tokens or 0)) if output_tokens is not None else 0, max(0, int(output_tokens or 0)) if output_tokens is not None else 0,
                    max(0, int(total_tokens or 0)) if total_tokens is not None else 0, max(0, int(total_tokens or 0)) if total_tokens is not None else 0,
                    now,
                    trace_id,
                ),
            )
            return
        conn.execute(
            """
            INSERT INTO memory_usage_audits (
                id, trace_id, chat_id, bot_key, call_type, status, user_query,
                memory_pack, selected_files_json, selected_sections_json,
                omitted_files_json, token_budget_used_estimate, confidence,
                needs_more_memory, reason, final_answer, input_tokens,
                output_tokens, total_tokens, created_at, updated_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                row_id,
                trace_id,
                *payload[:-1],
                now,
                payload[-1],
            ),
        )


def list_recent_memory_usage_audits(
    database_path: Path,
    *,
    days: int = 7,
    call_types: tuple[str, ...] = ("chat", "draft"),
    limit: int = 50,
    require_documents: bool = False,
) -> list[dict[str, Any]]:
    initialize_database(database_path)
    cutoff = utc_now_minus_days(days)
    params: list[Any] = [cutoff]
    clauses = ["created_at >= ?"]
    if call_types:
        placeholders = ",".join("?" for _ in call_types)
        clauses.append(f"call_type IN ({placeholders})")
        params.extend(call_types)
    if require_documents:
        clauses.append("selected_files_json LIKE ?")
        params.append("%documents/%")
    where_sql = " AND ".join(clauses)
    with connect_database(database_path) as conn:
        rows = conn.execute(
            f"""
            SELECT *
            FROM memory_usage_audits
            WHERE {where_sql}
            ORDER BY updated_at DESC, created_at DESC
            LIMIT ?
            """,
            (*params, max(1, int(limit))),
        ).fetchall()
    result: list[dict[str, Any]] = []
    for row in rows:
        result.append(
            {
                "id": str(row["id"]),
                "trace_id": str(row["trace_id"]),
                "chat_id": str(row["chat_id"]),
                "bot_key": str(row["bot_key"]),
                "call_type": str(row["call_type"]),
                "status": str(row["status"]),
                "user_query": str(row["user_query"]),
                "memory_pack": str(row["memory_pack"]),
                "selected_files": _from_json_list(str(row["selected_files_json"])),
                "selected_sections": _from_json_list(str(row["selected_sections_json"])),
                "omitted_files": _from_json_list(str(row["omitted_files_json"])),
                "token_budget_used_estimate": int(row["token_budget_used_estimate"]),
                "confidence": str(row["confidence"]),
                "needs_more_memory": bool(row["needs_more_memory"]),
                "reason": str(row["reason"]),
                "final_answer": str(row["final_answer"]),
                "input_tokens": int(row["input_tokens"]),
                "output_tokens": int(row["output_tokens"]),
                "total_tokens": int(row["total_tokens"]),
                "created_at": str(row["created_at"]),
                "updated_at": str(row["updated_at"]),
            }
        )
    return result
