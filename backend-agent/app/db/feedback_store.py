from __future__ import annotations

import json
import sqlite3
from datetime import datetime, timezone, timedelta
from typing import Any
from uuid import uuid4

from app.db.core import connect_database


def _now() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def _today_start() -> str:
    now = datetime.now(timezone(timedelta(hours=8)))
    return now.replace(hour=0, minute=0, second=0, microsecond=0).isoformat()


def save_feedback(
    database_path: Any,
    *,
    msg_id: str,
    chat_id: str,
    bot_key: str,
    user_id: str,
    result: str,
    reason: str = "",
    metadata_json: str = "{}",
) -> None:
    with connect_database(database_path) as conn:
        conn.execute(
            """
            INSERT INTO message_feedbacks (
                id, created_at, msg_id, chat_id, bot_key, user_id, result, reason, metadata_json
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (str(uuid4()), _now(), msg_id, chat_id, bot_key, user_id, result, reason, metadata_json),
        )


def get_feedback_stats(
    database_path: Any,
    *,
    chat_id: str = "",
    bot_key: str = "",
    days: int = 0,
) -> dict[str, Any]:
    with connect_database(database_path) as conn:
        where_clauses: list[str] = []
        params: list[Any] = []

        if days == 0:
            where_clauses.append("created_at >= ?")
            params.append(_today_start())
        elif days > 0:
            since = (datetime.now(timezone(timedelta(hours=8))) - timedelta(days=days)).isoformat()
            where_clauses.append("created_at >= ?")
            params.append(since)

        if chat_id:
            where_clauses.append("chat_id = ?")
            params.append(chat_id)
        if bot_key:
            where_clauses.append("bot_key = ?")
            params.append(bot_key)

        where = " AND ".join(where_clauses) if where_clauses else "1=1"

        total = conn.execute(
            f"SELECT COUNT(*) AS count FROM message_feedbacks WHERE {where}", params
        ).fetchone()["count"]

        useful = conn.execute(
            f"SELECT COUNT(*) AS count FROM message_feedbacks WHERE {where} AND result = 'useful'",
            params,
        ).fetchone()["count"]

        return {
            "total": total,
            "useful": useful,
            "useless": total - useful,
            "satisfaction_rate": round(useful / total * 100, 2) if total > 0 else 0,
            "days": days,
        }


def _get_bot_name(conn: sqlite3.Connection, bot_key: str) -> str:
    if not bot_key:
        return ""
    row = conn.execute(
        "SELECT name FROM bot_config WHERE bot_key = ?",
        (bot_key,),
    ).fetchone()
    return str(row["name"] or "") if row else ""


def batch_get_feedbacks_by_chat_ids(
    database_path: Any,
    chat_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    clean_ids = [str(cid or "").strip() for cid in chat_ids if str(cid or "").strip()]
    if not clean_ids:
        return {}
    placeholders = ",".join("?" for _ in clean_ids)
    with connect_database(database_path) as conn:
        rows = conn.execute(
            f"""
            SELECT id, created_at, msg_id, chat_id, bot_key, user_id, result, reason
            FROM message_feedbacks
            WHERE chat_id IN ({placeholders})
            ORDER BY created_at ASC
            """,
            clean_ids,
        ).fetchall()
    result_map: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        cid = str(row["chat_id"] or "")
        result_map.setdefault(cid, []).append({
            "id": str(row["id"] or ""),
            "created_at": str(row["created_at"] or ""),
            "msg_id": str(row["msg_id"] or ""),
            "chat_id": cid,
            "bot_key": str(row["bot_key"] or ""),
            "user_id": str(row["user_id"] or ""),
            "result": str(row["result"] or ""),
            "reason": str(row["reason"] or ""),
        })
    return result_map


def _get_chat_info(conn: sqlite3.Connection, chat_id: str, bot_key: str = "") -> dict[str, Any]:
    params: list[Any] = [chat_id]
    bot_clause = ""
    if bot_key:
        bot_clause = " AND bot_key = ?"
        params.append(bot_key)
    row = conn.execute(
        f"""
        SELECT chat_id, chat_name, display_name, chat_type, sender_id, sender_name,
               external_chat_id, conversation_kind, bot_key
        FROM conversations
        WHERE chat_id = ?{bot_clause}
        ORDER BY updated_at DESC
        LIMIT 1
        """,
        params,
    ).fetchone()
    if row:
        chat_type = row["chat_type"] or "unknown"
        conversation_kind = row["conversation_kind"] or "external"
        if chat_type == "unknown" and conversation_kind == "me":
            chat_type = "single"
        display_name = (
            row["display_name"]
            or row["chat_name"]
            or row["sender_name"]
            or row["external_chat_id"]
            or row["chat_id"]
            or ""
        )
        return {
            "chat_id": row["chat_id"] or chat_id,
            "chat_name": row["chat_name"] or "",
            "display_name": display_name,
            "chat_type": chat_type,
            "sender_id": row["sender_id"] or "",
            "sender_name": row["sender_name"] or "",
            "external_chat_id": row["external_chat_id"] or "",
            "conversation_kind": conversation_kind,
            "bot_key": row["bot_key"] or bot_key,
        }
    return {
        "chat_id": chat_id,
        "chat_name": "",
        "display_name": chat_id,
        "chat_type": "unknown",
        "sender_id": "",
        "sender_name": "",
        "external_chat_id": "",
        "conversation_kind": "external",
        "bot_key": bot_key,
    }


def _load_json_object(raw: Any) -> dict[str, Any]:
    if isinstance(raw, dict):
        return raw
    try:
        data = json.loads(str(raw or "{}"))
    except (TypeError, json.JSONDecodeError):
        return {}
    return data if isinstance(data, dict) else {}


def _iter_metadata_ids(metadata: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in ("trace_id", "feedback_id", "msg_id", "message_id", "id"):
        value = metadata.get(key)
        if isinstance(value, (str, int, float)):
            text = str(value).strip()
            if text:
                ids.append(text)
    return list(dict.fromkeys(ids))


def _chunked(values: list[str], size: int = 500) -> list[list[str]]:
    return [values[index:index + size] for index in range(0, len(values), size)]


def get_feedback_by_message_ids(
    database_path: Any,
    message_ids: list[str],
) -> dict[str, list[dict[str, Any]]]:
    clean_message_ids = list(dict.fromkeys(str(item or "").strip() for item in message_ids if str(item or "").strip()))
    if not clean_message_ids:
        return {}

    with connect_database(database_path) as conn:
        messages: dict[str, dict[str, str]] = {}
        candidate_index: dict[str, list[str]] = {}
        for chunk in _chunked(clean_message_ids):
            placeholders = ", ".join("?" for _ in chunk)
            rows = conn.execute(
                f"""
                SELECT id, chat_id, bot_key, metadata_json
                FROM chat_messages
                WHERE id IN ({placeholders})
                """,
                chunk,
            ).fetchall()
            for row in rows:
                message_id = str(row["id"] or "").strip()
                if not message_id:
                    continue
                metadata = _load_json_object(row["metadata_json"])
                candidates = [message_id, *_iter_metadata_ids(metadata)]
                messages[message_id] = {
                    "chat_id": str(row["chat_id"] or ""),
                    "bot_key": str(row["bot_key"] or ""),
                }
                for candidate in list(dict.fromkeys(candidates)):
                    candidate_index.setdefault(candidate, []).append(message_id)

        if not candidate_index:
            return {}

        feedback_rows: list[sqlite3.Row] = []
        candidate_ids = list(candidate_index)
        for chunk in _chunked(candidate_ids):
            placeholders = ", ".join("?" for _ in chunk)
            feedback_rows.extend(
                conn.execute(
                    f"""
                    SELECT id, created_at, msg_id, chat_id, bot_key, user_id, result, reason, metadata_json
                    FROM message_feedbacks
                    WHERE msg_id IN ({placeholders})
                    ORDER BY created_at DESC
                    """,
                    chunk,
                ).fetchall()
            )
        feedback_rows.sort(key=lambda row: str(row["created_at"] or ""), reverse=True)

    feedback_by_message_id: dict[str, list[dict[str, Any]]] = {}
    seen: set[tuple[str, str]] = set()
    for row in feedback_rows:
        msg_id = str(row["msg_id"] or "").strip()
        for message_id in candidate_index.get(msg_id, []):
            message = messages.get(message_id, {})
            feedback_chat_id = str(row["chat_id"] or "")
            feedback_bot_key = str(row["bot_key"] or "")
            if feedback_chat_id and message.get("chat_id") and feedback_chat_id != message["chat_id"]:
                continue
            if feedback_bot_key and message.get("bot_key") and feedback_bot_key != message["bot_key"]:
                continue
            key = (message_id, str(row["id"] or ""))
            if key in seen:
                continue
            seen.add(key)
            feedback_by_message_id.setdefault(message_id, []).append({
                "id": str(row["id"] or ""),
                "created_at": str(row["created_at"] or ""),
                "msg_id": msg_id,
                "chat_id": feedback_chat_id,
                "bot_key": feedback_bot_key,
                "user_id": str(row["user_id"] or ""),
                "result": str(row["result"] or ""),
                "reason": str(row["reason"] or ""),
                "metadata_json": str(row["metadata_json"] or "{}"),
            })
    return feedback_by_message_id


def _get_message_qa(conn: sqlite3.Connection, msg_id: str, chat_id: str, bot_key: str = "") -> dict[str, Any]:
    bot_clause = " AND bot_key = ?" if bot_key else ""
    bot_params: list[Any] = [bot_key] if bot_key else []
    answer_row = conn.execute(
        f"""
        SELECT content, sender_name, created_at, convert_status, convert_at FROM chat_messages
        WHERE chat_id = ?
          AND (id = ? OR metadata_json LIKE ?){bot_clause}
        ORDER BY created_at DESC LIMIT 1
        """,
        [chat_id, msg_id, f"%{msg_id}%", *bot_params],
    ).fetchone()
    if not answer_row:
        return {
            "question": "",
            "answer": "",
            "answer_sender": "",
            "answer_created_at": "",
            "answer_convert_status": "",
            "answer_convert_at": "",
        }
    answer = answer_row["content"] or ""
    answer_sender = answer_row["sender_name"] or ""
    bot_question_clause = " AND bot_key = ?" if bot_key else ""

    question_row = conn.execute(
        f"""
        SELECT content FROM chat_messages
        WHERE chat_id = ?
          AND direction = 'user'
          AND created_at < ?{bot_question_clause}
        ORDER BY created_at DESC LIMIT 1
        """,
        [chat_id, answer_row["created_at"], *bot_params],
    ).fetchone()
    question = question_row["content"] if question_row else ""

    return {
        "question": question,
        "answer": answer,
        "answer_sender": answer_sender,
        "answer_created_at": answer_row["created_at"] or "",
        "answer_convert_status": str(answer_row["convert_status"] or ""),
        "answer_convert_at": str(answer_row["convert_at"] or ""),
    }


def list_recent_feedback_review_samples(
    database_path: Any,
    *,
    result: str = "useless",
    days: int = 7,
    limit: int = 40,
    exclude_reviewed: bool = True,
) -> list[dict[str, Any]]:
    with connect_database(database_path) as conn:
        where_clauses: list[str] = []
        params: list[Any] = []
        if days > 0:
            since = (datetime.now(timezone(timedelta(hours=8))) - timedelta(days=days)).isoformat()
            where_clauses.append("created_at >= ?")
            params.append(since)
        if result:
            where_clauses.append("result = ?")
            params.append(result)
        if exclude_reviewed:
            where_clauses.append("(reviewed_at = '' OR reviewed_at IS NULL)")
        where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        rows = conn.execute(
            f"""
            SELECT id, created_at, msg_id, chat_id, bot_key, user_id, result, reason, reviewed_at, metadata_json
            FROM message_feedbacks
            {where}
            ORDER BY created_at DESC
            LIMIT ?
            """,
            params + [max(1, min(int(limit or 40), 200))],
        ).fetchall()

        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            chat_info = _get_chat_info(conn, item["chat_id"], item["bot_key"])
            qa = _get_message_qa(conn, item["msg_id"], chat_info["chat_id"], item["bot_key"])
            item["conversation_chat_id"] = chat_info["chat_id"]
            item["chat_display_name"] = chat_info["display_name"] or chat_info["chat_name"] or item["chat_id"]
            item["chat_type"] = chat_info["chat_type"]
            item["conversation_kind"] = chat_info["conversation_kind"]
            item["external_chat_id"] = chat_info["external_chat_id"]
            item["bot_name"] = _get_bot_name(conn, item["bot_key"]) or item["bot_key"]
            item["question"] = qa["question"]
            item["answer"] = qa["answer"]
            item["answer_sender"] = qa["answer_sender"]
            item["answer_created_at"] = qa.get("answer_created_at", "")
            item["answer_convert_status"] = qa.get("answer_convert_status", "")
            item["answer_convert_at"] = qa.get("answer_convert_at", "")
            item["review_status"] = "reviewed" if str(item.get("reviewed_at") or "").strip() else "pending"
            items.append(item)
        return items


def list_feedbacks(
    database_path: Any,
    *,
    result: str = "",
    days: int = 0,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    with connect_database(database_path) as conn:
        where_clauses: list[str] = []
        params: list[Any] = []

        if days == 0:
            where_clauses.append("created_at >= ?")
            params.append(_today_start())
        elif days > 0:
            since = (datetime.now(timezone(timedelta(hours=8))) - timedelta(days=days)).isoformat()
            where_clauses.append("created_at >= ?")
            params.append(since)

        if result:
            where_clauses.append("result = ?")
            params.append(result)

        where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        count = conn.execute(
            f"SELECT COUNT(*) AS count FROM message_feedbacks {where}", params
        ).fetchone()["count"]

        offset = (page - 1) * page_size
        rows = conn.execute(
            f"""
            SELECT id, created_at, msg_id, chat_id, bot_key, user_id, result, reason, reviewed_at, metadata_json
            FROM message_feedbacks
            {where}
            ORDER BY created_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [page_size, offset],
        ).fetchall()

        items = []
        for row in rows:
            item = dict(row)
            chat_info = _get_chat_info(conn, item["chat_id"], item["bot_key"])
            item["raw_chat_id"] = item["chat_id"]
            item["conversation_chat_id"] = chat_info["chat_id"]
            item["chat_type"] = chat_info["chat_type"]
            item["conversation_kind"] = chat_info["conversation_kind"]
            item["external_chat_id"] = chat_info["external_chat_id"]
            item["sender_id"] = chat_info["sender_id"]
            item["sender_name"] = chat_info["sender_name"]
            item["chat_display_name"] = chat_info["display_name"] or chat_info["chat_name"] or item["chat_id"]
            item["bot_name"] = _get_bot_name(conn, item["bot_key"]) or item["bot_key"]
            qa = _get_message_qa(conn, item["msg_id"], chat_info["chat_id"], item["bot_key"])
            item["question"] = qa["question"]
            item["answer"] = qa["answer"]
            item["answer_sender"] = qa["answer_sender"]
            item["answer_convert_status"] = qa.get("answer_convert_status", "")
            item["answer_convert_at"] = qa.get("answer_convert_at", "")
            item["review_status"] = "reviewed" if str(item.get("reviewed_at") or "").strip() else "pending"
            items.append(item)

        return {
            "total": count,
            "page": page,
            "page_size": page_size,
            "items": items,
        }


def list_feedbacks_by_message(
    database_path: Any,
    *,
    result: str = "",
    days: int = 0,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    from app.db.user_store import list_user_display_names

    with connect_database(database_path) as conn:
        where_clauses: list[str] = []
        params: list[Any] = []

        if days == 0:
            where_clauses.append("created_at >= ?")
            params.append(_today_start())
        elif days > 0:
            since = (datetime.now(timezone(timedelta(hours=8))) - timedelta(days=days)).isoformat()
            where_clauses.append("created_at >= ?")
            params.append(since)

        if result:
            where_clauses.append("result = ?")
            params.append(result)

        where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""

        msg_ids_rows = conn.execute(
            f"""
            SELECT msg_id, MAX(created_at) AS latest_at
            FROM message_feedbacks {where}
            GROUP BY msg_id
            ORDER BY latest_at DESC
            """,
            params,
        ).fetchall()
        all_msg_ids = [str(row["msg_id"] or "").strip() for row in msg_ids_rows if str(row["msg_id"] or "").strip()]

        total = len(all_msg_ids)
        page = max(1, int(page or 1))
        page_size = max(1, min(int(page_size or 20), 100))
        offset = (page - 1) * page_size
        paged_msg_ids = all_msg_ids[offset:offset + page_size]

        if not paged_msg_ids:
            return {"total": total, "page": page, "page_size": page_size, "items": []}

        placeholders = ",".join("?" for _ in paged_msg_ids)
        fb_rows = conn.execute(
            f"""
            SELECT id, created_at, msg_id, chat_id, bot_key, user_id, result, reason, reviewed_at, metadata_json
            FROM message_feedbacks
            WHERE msg_id IN ({placeholders})
            ORDER BY created_at ASC
            """,
            paged_msg_ids,
        ).fetchall()

        grouped: dict[str, list[dict[str, Any]]] = {}
        all_user_ids: list[str] = []
        for row in fb_rows:
            mid = str(row["msg_id"] or "").strip()
            uid = str(row["user_id"] or "").strip()
            if uid:
                all_user_ids.append(uid)
            grouped.setdefault(mid, []).append({
                "id": str(row["id"] or ""),
                "created_at": str(row["created_at"] or ""),
                "msg_id": mid,
                "chat_id": str(row["chat_id"] or ""),
                "bot_key": str(row["bot_key"] or ""),
                "user_id": uid,
                "result": str(row["result"] or ""),
                "reason": str(row["reason"] or ""),
                "reviewed_at": str(row["reviewed_at"] or ""),
            })

        user_display_names = list_user_display_names(database_path, list(dict.fromkeys(all_user_ids))) if all_user_ids else {}
        for fb_list in grouped.values():
            for fb in fb_list:
                fb["user_display_name"] = user_display_names.get(fb["user_id"], "")

        items: list[dict[str, Any]] = []
        for mid in paged_msg_ids:
            feedbacks = grouped.get(mid, [])
            if not feedbacks:
                continue
            primary = feedbacks[-1]
            chat_id = primary["chat_id"]
            bot_key = primary["bot_key"]
            chat_info = _get_chat_info(conn, chat_id, bot_key)
            qa = _get_message_qa(conn, mid, chat_info["chat_id"], bot_key)

            fb_results = set(str(fb.get("result") or "").strip().lower() for fb in feedbacks)
            has_useful = "useful" in fb_results
            has_useless = "useless" in fb_results
            if has_useful and has_useless:
                status = "mixed"
            elif has_useless:
                status = "useless"
            elif has_useful:
                status = "useful"
            else:
                status = ""

            useless_reasons = [
                str(fb.get("reason") or "").strip()
                for fb in feedbacks
                if str(fb.get("result") or "").strip().lower() == "useless" and str(fb.get("reason") or "").strip()
            ]
            reviewable_feedbacks = [
                fb for fb in feedbacks
                if str(fb.get("result") or "").strip().lower() == "useless"
            ]
            reviewed_feedbacks = [fb for fb in reviewable_feedbacks if str(fb.get("reviewed_at") or "").strip()]
            reviewed_count = len(reviewed_feedbacks)
            reviewable_count = len(reviewable_feedbacks)
            if reviewable_count > 0 and reviewed_count == reviewable_count:
                review_status = "reviewed"
            elif reviewed_count > 0:
                review_status = "partial"
            else:
                review_status = "pending"
            latest_reviewed_at = max((str(fb.get("reviewed_at") or "") for fb in reviewed_feedbacks), default="")

            items.append({
                "msg_id": mid,
                "chat_id": chat_id,
                "raw_chat_id": chat_id,
                "conversation_chat_id": chat_info["chat_id"],
                "chat_type": chat_info["chat_type"],
                "conversation_kind": chat_info["conversation_kind"],
                "external_chat_id": chat_info["external_chat_id"],
                "sender_id": chat_info["sender_id"],
                "sender_name": chat_info["sender_name"],
                "chat_display_name": chat_info["display_name"] or chat_info["chat_name"] or chat_id,
                "bot_key": bot_key,
                "bot_name": _get_bot_name(conn, bot_key) or bot_key,
                "question": qa["question"],
                "answer": qa["answer"],
                "answer_sender": qa["answer_sender"],
                "answer_convert_status": qa.get("answer_convert_status", ""),
                "answer_convert_at": qa.get("answer_convert_at", ""),
                "memory_convert_status": qa.get("answer_convert_status", ""),
                "memory_convert_at": qa.get("answer_convert_at", ""),
                "feedback_status": status,
                "feedback_count": len(feedbacks),
                "useful_count": sum(1 for fb in feedbacks if str(fb.get("result") or "").strip().lower() == "useful"),
                "useless_count": sum(1 for fb in feedbacks if str(fb.get("result") or "").strip().lower() == "useless"),
                "useless_reasons": "；".join(useless_reasons) if useless_reasons else "",
                "review_status": review_status,
                "reviewed_count": reviewed_count,
                "review_feedback_count": reviewable_count,
                "unreviewed_count": max(0, reviewable_count - reviewed_count),
                "latest_reviewed_at": latest_reviewed_at,
                "feedbacks": feedbacks,
                "latest_feedback_at": primary["created_at"],
            })

        return {
            "total": total,
            "page": page,
            "page_size": page_size,
            "items": items,
        }


def count_recent_useless_feedbacks(
    conn: sqlite3.Connection,
    *,
    chat_id: str,
    bot_key: str,
    window_minutes: int,
) -> int:
    since = (datetime.now(timezone(timedelta(hours=8))) - timedelta(minutes=window_minutes)).isoformat()
    row = conn.execute(
        """
        SELECT COUNT(*) AS count
        FROM message_feedbacks
        WHERE chat_id = ?
          AND bot_key = ?
          AND result = 'useless'
          AND created_at >= ?
        """,
        (chat_id, bot_key, since),
    ).fetchone()
    return int(row["count"]) if row else 0


def should_send_alert(
    conn: sqlite3.Connection,
    *,
    chat_id: str,
    bot_key: str,
    cooldown_minutes: int,
) -> bool:
    since = (datetime.now(timezone(timedelta(hours=8))) - timedelta(minutes=cooldown_minutes)).isoformat()
    row = conn.execute(
        """
        SELECT 1
        FROM feedback_alert_log
        WHERE chat_id = ?
          AND bot_key = ?
          AND alert_type = 'useless_spike'
          AND notified_at >= ?
        LIMIT 1
        """,
        (chat_id, bot_key, since),
    ).fetchone()
    return row is None


def record_alert_sent(
    conn: sqlite3.Connection,
    *,
    chat_id: str,
    bot_key: str,
    threshold: int,
    window_minutes: int,
    feedback_count: int,
    metadata: dict[str, Any] | None = None,
) -> None:
    now = _now()
    conn.execute(
        """
        INSERT INTO feedback_alert_log (
            id, created_at, chat_id, bot_key, alert_type, threshold,
            window_minutes, feedback_count, notified_at, metadata_json
        ) VALUES (?, ?, ?, ?, 'useless_spike', ?, ?, ?, ?, ?)
        """,
        (
            str(uuid4()),
            now,
            chat_id,
            bot_key,
            threshold,
            window_minutes,
            feedback_count,
            now,
            json.dumps(metadata or {}, ensure_ascii=False),
        ),
    )


def get_recent_useless_feedback_context(
    database_path: Any,
    *,
    chat_id: str,
    bot_key: str,
    window_minutes: int,
    limit: int = 5,
) -> dict[str, Any]:
    with connect_database(database_path) as conn:
        chat_info = _get_chat_info(conn, chat_id, bot_key)
        since = (datetime.now(timezone(timedelta(hours=8))) - timedelta(minutes=window_minutes)).isoformat()
        rows = conn.execute(
            """
            SELECT id, created_at, msg_id, chat_id, bot_key, user_id, result, reason, metadata_json
            FROM message_feedbacks
            WHERE chat_id = ?
              AND bot_key = ?
              AND result = 'useless'
              AND created_at >= ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (chat_info["chat_id"], bot_key, since, max(1, min(int(limit or 5), 20))),
        ).fetchall()
        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            qa = _get_message_qa(conn, item["msg_id"], chat_info["chat_id"], bot_key)
            item["question"] = qa["question"]
            item["answer"] = qa["answer"]
            item["answer_sender"] = qa["answer_sender"]
            items.append(item)
        return {
            "chat": chat_info,
            "bot_name": _get_bot_name(conn, bot_key) or bot_key,
            "items": items,
        }


def list_feedback_alerts(
    database_path: Any,
    *,
    days: int = 0,
    page: int = 1,
    page_size: int = 20,
) -> dict[str, Any]:
    with connect_database(database_path) as conn:
        where_clauses: list[str] = []
        params: list[Any] = []

        if days == 0:
            where_clauses.append("created_at >= ?")
            params.append(_today_start())
        elif days > 0:
            since = (datetime.now(timezone(timedelta(hours=8))) - timedelta(days=days)).isoformat()
            where_clauses.append("created_at >= ?")
            params.append(since)

        where = f"WHERE {' AND '.join(where_clauses)}" if where_clauses else ""
        count = conn.execute(
            f"SELECT COUNT(*) AS count FROM feedback_alert_log {where}",
            params,
        ).fetchone()["count"]
        page = max(1, int(page or 1))
        page_size = max(1, min(int(page_size or 20), 100))
        offset = (page - 1) * page_size
        rows = conn.execute(
            f"""
            SELECT id, created_at, chat_id, bot_key, alert_type, threshold,
                   window_minutes, feedback_count, notified_at, metadata_json
            FROM feedback_alert_log
            {where}
            ORDER BY notified_at DESC
            LIMIT ? OFFSET ?
            """,
            params + [page_size, offset],
        ).fetchall()

        items: list[dict[str, Any]] = []
        for row in rows:
            item = dict(row)
            chat_info = _get_chat_info(conn, item["chat_id"], item["bot_key"])
            item["conversation_chat_id"] = chat_info["chat_id"]
            item["chat_type"] = chat_info["chat_type"]
            item["conversation_kind"] = chat_info["conversation_kind"]
            item["external_chat_id"] = chat_info["external_chat_id"]
            item["chat_display_name"] = chat_info["display_name"] or chat_info["chat_name"] or item["chat_id"]
            item["bot_name"] = _get_bot_name(conn, item["bot_key"]) or item["bot_key"]
            try:
                item["metadata"] = json.loads(str(item.get("metadata_json") or "{}"))
            except (TypeError, json.JSONDecodeError):
                item["metadata"] = {}
            items.append(item)

        return {
            "total": int(count),
            "page": page,
            "page_size": page_size,
            "items": items,
        }


def cleanup_old_feedbacks(database_path: Any, retention_days: int = 30) -> int:
    with connect_database(database_path) as conn:
        cutoff = (datetime.now(timezone(timedelta(hours=8))) - timedelta(days=retention_days)).isoformat()
        count = conn.execute(
            "SELECT COUNT(*) AS count FROM message_feedbacks WHERE created_at < ?",
            (cutoff,),
        ).fetchone()["count"]
        conn.execute("DELETE FROM message_feedbacks WHERE created_at < ?", (cutoff,))
        return count


def mark_feedbacks_reviewed(database_path: Any, feedback_ids: list[str]) -> int:
    if not feedback_ids:
        return 0
    now = _now()
    clean_ids = [str(fid).strip() for fid in feedback_ids if str(fid).strip()]
    if not clean_ids:
        return 0
    with connect_database(database_path) as conn:
        updated = 0
        for chunk in _chunked(clean_ids):
            placeholders = ",".join("?" for _ in chunk)
            cursor = conn.execute(
                f"UPDATE message_feedbacks SET reviewed_at = ? WHERE id IN ({placeholders}) AND (reviewed_at = '' OR reviewed_at IS NULL)",
                [now, *chunk],
            )
            updated += cursor.rowcount
        return updated
