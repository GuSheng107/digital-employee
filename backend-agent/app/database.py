from __future__ import annotations

"""数据库路径解析与初始化工具模块。

提供数据库信息查询、概览统计和数据库优化清理等功能，
包括消息/日志/任务的过期清理、附件文件回收和 SQLite 维护操作。
"""

import sqlite3
from pathlib import Path
from typing import Any

from app.db.core import (
    connect_database,
    initialize_database,
    run_sqlite_maintenance,
)
from app.manual_reply_attachments import ATTACHMENTS_DIR_NAME
from app.utils import DATABASE_FILENAME, default_database_path, utc_now, utc_now_minus_days


def _cleanup_attachment_file_store(
    conn: sqlite3.Connection,
    *,
    project_root: Path,
    referenced_storage_names: set[str],
) -> int:
    attachments_dir = project_root / ATTACHMENTS_DIR_NAME
    if not attachments_dir.exists() or not attachments_dir.is_dir():
        return 0
    removed_files = 0
    for attachment_path in attachments_dir.iterdir():
        if not attachment_path.is_file():
            continue
        if attachment_path.name in referenced_storage_names:
            continue
        try:
            attachment_path.unlink()
        except OSError:
            continue
        removed_files += 1
    return removed_files


def _collect_referenced_attachment_storage_names(conn: sqlite3.Connection) -> set[str]:
    storage_names: set[str] = set()
    for row in conn.execute(
        """
        SELECT metadata_json
        FROM manual_reply_commands
        WHERE metadata_json LIKE '%storage_name%'
        """
    ).fetchall():
        _collect_attachment_names_from_metadata(
            storage_names,
            str(row["metadata_json"] or ""),
            field="attachments",
        )
    for row in conn.execute(
        """
        SELECT metadata_json
        FROM chat_messages
        WHERE metadata_json LIKE '%storage_name%' OR metadata_json LIKE '%manual-reply-attachments/%'
        """
    ).fetchall():
        _collect_attachment_names_from_metadata(
            storage_names,
            str(row["metadata_json"] or ""),
            field="parts",
        )
    return storage_names


def _collect_attachment_names_from_metadata(
    storage_names: set[str],
    metadata_json: str,
    *,
    field: str,
) -> None:
    import json

    try:
        metadata = json.loads(metadata_json or "{}")
    except json.JSONDecodeError:
        return
    items = metadata.get(field)
    if not isinstance(items, list):
        return
    for item in items:
        if not isinstance(item, dict):
            continue
        storage_name = str(item.get("storage_name") or "").strip()
        if storage_name:
            storage_names.add(storage_name)
            continue
        url = str(item.get("url") or "").strip()
        prefix = "/api/manual-reply-attachments/"
        if not url.startswith(prefix):
            continue
        candidate = url[len(prefix):].split("?", 1)[0].strip()
        if candidate:
            storage_names.add(candidate)


def get_database_info(path: Path) -> dict[str, Any]:
    database_path = initialize_database(path)
    with connect_database(database_path) as conn:
        tables = [
            str(row["name"])
            for row in conn.execute(
                "SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"
            ).fetchall()
        ]
    return {
        "path": str(database_path),
        "exists": True,
        "tables": tables,
    }


def get_database_overview(path: Path) -> dict[str, Any]:
    database_path = initialize_database(path)
    size_bytes = database_path.stat().st_size if database_path.exists() else 0
    ai_work_cutoff = utc_now_minus_days(30)
    with connect_database(database_path) as conn:
        conversations = conn.execute("SELECT COUNT(*) AS count FROM conversations").fetchone()["count"]
        messages = conn.execute("SELECT COUNT(*) AS count FROM chat_messages").fetchone()["count"]
        logs = conn.execute("SELECT COUNT(*) AS count FROM project_logs").fetchone()["count"]
        recent_ai_tasks = conn.execute(
            "SELECT COUNT(*) AS count FROM ai_work_items WHERE started_at >= ?",
            (ai_work_cutoff,),
        ).fetchone()["count"]
        manual_replies = conn.execute(
            "SELECT COUNT(*) AS count FROM chat_messages WHERE direction = 'bot' AND reply_source = 'manual'"
        ).fetchone()["count"]
        ai_replies = conn.execute(
            "SELECT COUNT(*) AS count FROM chat_messages WHERE direction = 'bot' AND reply_source = 'ai'"
        ).fetchone()["count"]
        uploaded_documents = conn.execute("SELECT COUNT(*) AS count FROM uploaded_documents").fetchone()["count"]
        converted_documents = conn.execute("SELECT COUNT(*) AS count FROM uploaded_documents WHERE convert_status = 'converted'").fetchone()["count"]
        converted_messages = conn.execute("SELECT COUNT(*) AS count FROM chat_messages WHERE convert_status = 'converted'").fetchone()["count"]
        unconverted_messages = conn.execute("SELECT COUNT(*) AS count FROM chat_messages WHERE convert_status = 'unconverted' AND direction = 'bot'").fetchone()["count"]
        memory_update_count = conn.execute(
            "SELECT COUNT(*) AS count FROM scheduled_tasks WHERE handler_name = 'memory_update' AND last_run_status = 'completed'",
        ).fetchone()["count"]
        document_extraction_count = conn.execute(
            "SELECT COUNT(*) AS count FROM scheduled_tasks WHERE handler_name = 'document_memory_extraction' AND last_run_status = 'completed'",
        ).fetchone()["count"]
        bot_count = conn.execute("SELECT COUNT(*) AS count FROM bot_config WHERE deleted_at = ''").fetchone()["count"]
        enabled_bot_count = conn.execute(
            "SELECT COUNT(*) AS count FROM bot_config WHERE deleted_at = '' AND is_active = 1"
        ).fetchone()["count"]
        ai_task_total = conn.execute("SELECT COUNT(*) AS count FROM ai_work_items").fetchone()["count"]
        ai_task_completed = conn.execute(
            "SELECT COUNT(*) AS count FROM ai_work_items WHERE status = 'completed'"
        ).fetchone()["count"]
        ai_task_failed = conn.execute(
            "SELECT COUNT(*) AS count FROM ai_work_items WHERE status = 'failed'"
        ).fetchone()["count"]
        ai_task_cancelled = conn.execute(
            "SELECT COUNT(*) AS count FROM ai_work_items WHERE status = 'cancelled'"
        ).fetchone()["count"]
        ai_task_running = conn.execute(
            "SELECT COUNT(*) AS count FROM ai_work_items WHERE status IN ('queued', 'running', 'cancel_requested')"
        ).fetchone()["count"]
        enabled_periodic_tasks = conn.execute(
            "SELECT COUNT(*) AS count FROM scheduled_tasks WHERE task_type = 'periodic' AND is_enabled = 1"
        ).fetchone()["count"]
        enabled_one_time_tasks = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM scheduled_tasks
            WHERE task_type = 'one_time'
              AND is_enabled = 1
              AND run_state IN ('pending', 'running')
              AND next_run_at != ''
            """
        ).fetchone()["count"]
        memory_pack_injection_success_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM memory_usage_audits
            WHERE call_type = 'chat'
              AND TRIM(memory_pack) != ''
              AND status = 'success'
            """
        ).fetchone()["count"]
        memory_pack_injection_failed_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM memory_usage_audits
            WHERE call_type = 'chat'
              AND TRIM(memory_pack) != ''
              AND status = 'failed'
            """
        ).fetchone()["count"]
    return {
        "path": str(database_path),
        "size_bytes": int(size_bytes),
        "conversations": int(conversations),
        "messages": int(messages),
        "logs": int(logs),
        "recent_ai_tasks": int(recent_ai_tasks),
        "bot_count": int(bot_count),
        "enabled_bot_count": int(enabled_bot_count),
        "active_bot_count": int(enabled_bot_count),
        "avg_messages_per_conversation": round((int(messages) / int(conversations)), 1) if conversations else 0,
        "enabled_periodic_tasks": int(enabled_periodic_tasks),
        "enabled_one_time_tasks": int(enabled_one_time_tasks),
        "manual_replies": int(manual_replies),
        "ai_replies": int(ai_replies),
        "ai_task_total": int(ai_task_total),
        "ai_task_completed": int(ai_task_completed),
        "ai_task_failed": int(ai_task_failed),
        "ai_task_cancelled": int(ai_task_cancelled),
        "ai_task_running": int(ai_task_running),
        "uploaded_documents": int(uploaded_documents),
        "converted_documents": int(converted_documents),
        "document_conversion_rate": round((int(converted_documents) / int(uploaded_documents)) * 100, 1) if uploaded_documents else 0,
        "converted_messages": int(converted_messages),
        "unconverted_messages": int(unconverted_messages),
        "message_conversion_rate": round((int(converted_messages) / int(messages)) * 100, 1) if messages else 0,
        "memory_update_count": int(memory_update_count),
        "document_extraction_count": int(document_extraction_count),
        "memory_pack_injection_success_count": int(memory_pack_injection_success_count),
        "memory_pack_injection_failed_count": int(memory_pack_injection_failed_count),
    }


def optimize_database(
    path: Path,
    *,
    retention_days: int = 30,
    log_retention_days: int = 15,
    ai_work_retention_days: int = 30,
    memory_usage_audit_retention_days: int = 30,
    token_usage_retention_days: int = 30,
    one_time_task_retention_days: int = 30,
    feedback_retention_days: int = 30,
) -> dict[str, Any]:
    database_path = initialize_database(path)
    project_root = database_path.parent.parent
    cutoff = utc_now_minus_days(retention_days)
    log_cutoff = utc_now_minus_days(log_retention_days)
    ai_work_cutoff = utc_now_minus_days(ai_work_retention_days)
    memory_usage_audit_cutoff = utc_now_minus_days(memory_usage_audit_retention_days)
    token_usage_cutoff = utc_now_minus_days(token_usage_retention_days)
    one_time_task_cutoff = utc_now_minus_days(one_time_task_retention_days)
    feedback_cutoff = utc_now_minus_days(feedback_retention_days)
    before_size = database_path.stat().st_size if database_path.exists() else 0
    with connect_database(database_path) as conn:
        message_count = conn.execute(
            "SELECT COUNT(*) AS count FROM chat_messages WHERE created_at < ?",
            (cutoff,),
        ).fetchone()["count"]
        conversation_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM conversations
            WHERE COALESCE(NULLIF(last_message_at, ''), created_at) < ?
            """,
            (cutoff,),
        ).fetchone()["count"]
        manual_reply_count = conn.execute(
            """
            SELECT COUNT(*) AS count
            FROM manual_reply_commands
            WHERE conversation_chat_id IN (
                SELECT chat_id
                FROM conversations
                WHERE COALESCE(NULLIF(last_message_at, ''), created_at) < ?
            )
            """,
            (cutoff,),
        ).fetchone()["count"]
        log_count = conn.execute(
            "SELECT COUNT(*) AS count FROM project_logs WHERE created_at < ?",
            (log_cutoff,),
        ).fetchone()["count"]
        conn.execute(
            "DELETE FROM conversation_context_summaries WHERE last_message_at < ?",
            (cutoff,),
        )
        conn.execute("DELETE FROM chat_messages WHERE created_at < ?", (cutoff,))
        conn.execute(
            """
            DELETE FROM manual_reply_commands
            WHERE conversation_chat_id IN (
                SELECT chat_id
                FROM conversations
                WHERE COALESCE(NULLIF(last_message_at, ''), created_at) < ?
            )
            """,
            (cutoff,),
        )
        conn.execute(
            "DELETE FROM conversations WHERE COALESCE(NULLIF(last_message_at, ''), created_at) < ?",
            (cutoff,),
        )
        conn.execute("DELETE FROM project_logs WHERE created_at < ?", (log_cutoff,))

        ai_work_count = conn.execute(
            "SELECT COUNT(*) AS count FROM ai_work_items WHERE status NOT IN ('queued', 'running', 'cancel_requested') AND finished_at < ?",
            (ai_work_cutoff,),
        ).fetchone()["count"]
        conn.execute(
            "DELETE FROM ai_work_items WHERE status NOT IN ('queued', 'running', 'cancel_requested') AND finished_at < ?",
            (ai_work_cutoff,),
        )
        memory_usage_audit_count = conn.execute(
            "SELECT COUNT(*) AS count FROM memory_usage_audits WHERE updated_at < ?",
            (memory_usage_audit_cutoff,),
        ).fetchone()["count"]
        conn.execute(
            "DELETE FROM memory_usage_audits WHERE updated_at < ?",
            (memory_usage_audit_cutoff,),
        )
        token_usage_count = conn.execute(
            "SELECT COUNT(*) AS count FROM token_usage WHERE created_at < ?",
            (token_usage_cutoff,),
        ).fetchone()["count"]
        conn.execute("DELETE FROM token_usage WHERE created_at < ?", (token_usage_cutoff,))

        feedback_count = conn.execute(
            "SELECT COUNT(*) AS count FROM message_feedbacks WHERE created_at < ?",
            (feedback_cutoff,),
        ).fetchone()["count"]
        conn.execute("DELETE FROM message_feedbacks WHERE created_at < ?", (feedback_cutoff,))
        feedback_alert_count = conn.execute(
            "SELECT COUNT(*) AS count FROM feedback_alert_log WHERE created_at < ?",
            (feedback_cutoff,),
        ).fetchone()["count"]
        conn.execute("DELETE FROM feedback_alert_log WHERE created_at < ?", (feedback_cutoff,))

        one_time_task_count = conn.execute(
            "SELECT COUNT(*) AS count FROM scheduled_tasks WHERE task_type = 'one_time' AND last_run_status IN ('completed', 'failed') AND last_run_at != '' AND last_run_at < ?",
            (one_time_task_cutoff,),
        ).fetchone()["count"]
        conn.execute(
            "DELETE FROM scheduled_tasks WHERE task_type = 'one_time' AND last_run_status IN ('completed', 'failed') AND last_run_at != '' AND last_run_at < ?",
            (one_time_task_cutoff,),
        )
        disabled_periodic_count = conn.execute(
            "SELECT COUNT(*) AS count FROM scheduled_tasks WHERE task_type = 'periodic' AND is_enabled = 0 AND handler_name NOT IN ('memory_update', 'self_review_chat_memory', 'self_review_document_memory', 'database_cleanup') AND updated_at != '' AND updated_at < ?",
            (cutoff,),
        ).fetchone()["count"]
        conn.execute(
            "DELETE FROM scheduled_tasks WHERE task_type = 'periodic' AND is_enabled = 0 AND handler_name NOT IN ('memory_update', 'self_review_chat_memory', 'self_review_document_memory', 'database_cleanup') AND updated_at != '' AND updated_at < ?",
            (cutoff,),
        )

        deleted_bot_rows = conn.execute(
            "SELECT bot_key FROM bot_config WHERE deleted_at != '' AND deleted_at < ?",
            (cutoff,),
        ).fetchall()
        deleted_bot_count = len(deleted_bot_rows)
        if deleted_bot_count > 0:
            deleted_bot_keys = [row["bot_key"] for row in deleted_bot_rows]
            placeholders = ",".join("?" for _ in deleted_bot_keys)
            conn.execute(f"DELETE FROM bot_skill_mapping WHERE bot_key IN ({placeholders})", deleted_bot_keys)
            conn.execute(f"DELETE FROM bot_mcp_mapping WHERE bot_key IN ({placeholders})", deleted_bot_keys)
            conn.execute(f"DELETE FROM conversations WHERE bot_key IN ({placeholders})", deleted_bot_keys)
            conn.execute(f"DELETE FROM chat_messages WHERE bot_key IN ({placeholders})", deleted_bot_keys)
            conn.execute(f"DELETE FROM manual_reply_commands WHERE bot_key IN ({placeholders})", deleted_bot_keys)
            conn.execute(f"DELETE FROM bot_config WHERE bot_key IN ({placeholders})", deleted_bot_keys)

        referenced_attachment_storage_names = _collect_referenced_attachment_storage_names(conn)
        removed_attachment_files = _cleanup_attachment_file_store(
            conn,
            project_root=project_root,
            referenced_storage_names=referenced_attachment_storage_names,
        )
    run_sqlite_maintenance(database_path)
    after_size = database_path.stat().st_size if database_path.exists() else 0
    return {
        "retention_days": retention_days,
        "cutoff": cutoff,
        "log_retention_days": log_retention_days,
        "log_cutoff": log_cutoff,
        "ai_work_retention_days": ai_work_retention_days,
        "memory_usage_audit_retention_days": memory_usage_audit_retention_days,
        "token_usage_retention_days": token_usage_retention_days,
        "one_time_task_retention_days": one_time_task_retention_days,
        "removed_messages": int(message_count),
        "removed_conversations": int(conversation_count),
        "removed_manual_reply_commands": int(manual_reply_count),
        "removed_logs": int(log_count),
        "removed_ai_work_items": int(ai_work_count),
        "removed_memory_usage_audits": int(memory_usage_audit_count),
        "removed_token_usage": int(token_usage_count),
        "removed_feedbacks": int(feedback_count),
        "removed_feedback_alerts": int(feedback_alert_count),
        "removed_one_time_tasks": int(one_time_task_count),
        "removed_disabled_periodic_tasks": int(disabled_periodic_count),
        "removed_manual_reply_attachments": int(removed_attachment_files),
        "removed_attachment_mappings": 0,
        "removed_deleted_bots": deleted_bot_count,
        "before_size_bytes": int(before_size),
        "after_size_bytes": int(after_size),
        "saved_bytes": max(0, int(before_size) - int(after_size)),
    }
