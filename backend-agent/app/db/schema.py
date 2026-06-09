from __future__ import annotations

import sqlite3
from datetime import datetime, timedelta, timezone


_DEFAULT_ADMIN_PASSWORD_HASH = (
    "pbkdf2_sha256$210000$d3db1676d5ee4be4a880d5b9f76e37ad$"
    "ae86dc47cdee88a2935f655bfb1315c026fd1d02abd80bf9fcbf962acb32330b"
)


def _schema_now() -> str:
    return datetime.now(timezone(timedelta(hours=8))).isoformat()


def _clean_identifier(value: str) -> str:
    cleaned = "".join(
        char
        for char in value.strip()
        if char.isalnum() or char in {"_", "-"}
    )
    return cleaned[:80]


def _apply_schema(conn: sqlite3.Connection) -> None:
    conn.executescript(
        """
        CREATE TABLE IF NOT EXISTS agent_provider_config (
            provider_key TEXT PRIMARY KEY,
            label TEXT NOT NULL,
            provider_type TEXT NOT NULL,
            model TEXT NOT NULL,
            base_url TEXT NOT NULL,
            api_key TEXT NOT NULL,
            temperature REAL NOT NULL,
            timeout_seconds INTEGER NOT NULL,
            max_retries INTEGER NOT NULL,
            model_kwargs_json TEXT NOT NULL DEFAULT '',
            capabilities_json TEXT NOT NULL DEFAULT '',
            built_in_tools_json TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL,
            last_test_status TEXT NOT NULL DEFAULT '',
            last_test_time TEXT NOT NULL DEFAULT '',
            last_test_trace_id TEXT NOT NULL DEFAULT '',
            provider_name TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS skill_config (
            skill_name TEXT PRIMARY KEY,
            display_name TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 0,
            description TEXT NOT NULL DEFAULT '',
            relative_path TEXT NOT NULL DEFAULT '',
            source TEXT NOT NULL DEFAULT 'local',
            scope TEXT NOT NULL DEFAULT 'bot',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS user_profile (
            user_id TEXT PRIMARY KEY,
            display_name TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS console_users (
            username TEXT PRIMARY KEY,
            display_name TEXT NOT NULL DEFAULT '',
            role TEXT NOT NULL,
            password_hash TEXT NOT NULL,
            is_active INTEGER NOT NULL DEFAULT 1,
            active_session_id TEXT NOT NULL DEFAULT '',
            active_session_expires_at INTEGER NOT NULL DEFAULT 0,
            last_login_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_console_users_role
            ON console_users(role);

        CREATE TABLE IF NOT EXISTS conversations (
            chat_id TEXT PRIMARY KEY,
            chat_name TEXT NOT NULL,
            display_name TEXT NOT NULL DEFAULT '',
            chat_type TEXT NOT NULL DEFAULT 'unknown',
            sender_id TEXT NOT NULL DEFAULT '',
            sender_name TEXT NOT NULL DEFAULT '',
            last_message_at TEXT NOT NULL DEFAULT '',
            deleted_at TEXT NOT NULL DEFAULT '',
            bot_key TEXT NOT NULL DEFAULT 'default',
            external_chat_id TEXT NOT NULL DEFAULT '',
            conversation_kind TEXT NOT NULL DEFAULT 'external',
            pinned INTEGER NOT NULL DEFAULT 0,
            pin_rank INTEGER NOT NULL DEFAULT 0,
            unread_count INTEGER NOT NULL DEFAULT 0,
            last_context_compressed_at TEXT NOT NULL DEFAULT '',
            reply_mode TEXT NOT NULL DEFAULT 'manual',
            conversation_status TEXT NOT NULL DEFAULT 'active',
            last_send_error TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS chat_messages (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            direction TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            chat_name TEXT NOT NULL,
            sender_id TEXT NOT NULL,
            sender_name TEXT NOT NULL,
            content TEXT NOT NULL,
            msg_type TEXT NOT NULL,
            status TEXT NOT NULL,
            reply_status TEXT NOT NULL DEFAULT 'unreplied',
            reply_source TEXT NOT NULL DEFAULT '',
            bot_key TEXT NOT NULL DEFAULT 'default',
            external_chat_id TEXT NOT NULL DEFAULT '',
            conversation_kind TEXT NOT NULL DEFAULT 'external',
            convert_status TEXT NOT NULL DEFAULT 'unconverted',
            convert_at TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}',
            FOREIGN KEY (chat_id) REFERENCES conversations(chat_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_chat_messages_chat_time
            ON chat_messages(chat_id, created_at);

        CREATE INDEX IF NOT EXISTS idx_chat_messages_bot_key
            ON chat_messages(bot_key);

        CREATE INDEX IF NOT EXISTS idx_chat_messages_created_at
            ON chat_messages(created_at);

        CREATE INDEX IF NOT EXISTS idx_conversations_bot_key
            ON conversations(bot_key);

        CREATE TABLE IF NOT EXISTS conversation_context_summaries (
            chat_id TEXT NOT NULL,
            sender_id TEXT NOT NULL,
            summary TEXT NOT NULL,
            covered_message_count INTEGER NOT NULL,
            last_message_at TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (chat_id, sender_id),
            FOREIGN KEY (chat_id) REFERENCES conversations(chat_id) ON DELETE CASCADE
        );

        CREATE INDEX IF NOT EXISTS idx_context_summaries_chat_sender
            ON conversation_context_summaries(chat_id, sender_id);

        CREATE TABLE IF NOT EXISTS manual_reply_commands (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            chat_name TEXT NOT NULL,
            content TEXT NOT NULL,
            status TEXT NOT NULL,
            error TEXT NOT NULL DEFAULT '',
            bot_key TEXT NOT NULL DEFAULT 'default',
            conversation_chat_id TEXT NOT NULL DEFAULT '',
            external_chat_id TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_manual_reply_status
            ON manual_reply_commands(status, created_at);

        CREATE TABLE IF NOT EXISTS project_logs (
            id TEXT PRIMARY KEY,
            trace_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            category TEXT NOT NULL DEFAULT 'system',
            level TEXT NOT NULL,
            source TEXT NOT NULL,
            message TEXT NOT NULL,
            detail TEXT NOT NULL DEFAULT '',
            error_code TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_project_logs_trace
            ON project_logs(trace_id);

        CREATE INDEX IF NOT EXISTS idx_project_logs_created
            ON project_logs(created_at);

        CREATE INDEX IF NOT EXISTS idx_project_logs_category
            ON project_logs(category);

        CREATE TABLE IF NOT EXISTS ai_work_items (
            trace_id TEXT PRIMARY KEY,
            status TEXT NOT NULL,
            chat_id TEXT NOT NULL DEFAULT '',
            chat_name TEXT NOT NULL DEFAULT '',
            question TEXT NOT NULL DEFAULT '',
            answer TEXT NOT NULL DEFAULT '',
            error TEXT NOT NULL DEFAULT '',
            stage TEXT NOT NULL DEFAULT '',
            cancel_requested INTEGER NOT NULL DEFAULT 0,
            started_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            finished_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS uploaded_documents (
            id TEXT PRIMARY KEY,
            filename TEXT NOT NULL,
            storage_name TEXT NOT NULL,
            storage_path TEXT,
            file_size INTEGER NOT NULL,
            file_type TEXT NOT NULL,
            mime_type TEXT,
            parse_status TEXT NOT NULL DEFAULT 'pending',
            parsed_at TEXT,
            parse_error TEXT,
            convert_status TEXT NOT NULL DEFAULT 'unconverted',
            convert_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS scheduled_tasks (
            task_key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            task_scope TEXT NOT NULL DEFAULT 'system',
            task_type TEXT NOT NULL DEFAULT 'periodic',
            executor_kind TEXT NOT NULL DEFAULT 'builtin',
            executor_id TEXT NOT NULL DEFAULT '',
            handler_name TEXT NOT NULL DEFAULT '',
            schedule_type TEXT NOT NULL DEFAULT 'interval_days',
            schedule_value INTEGER NOT NULL DEFAULT 0,
            schedule_time TEXT NOT NULL DEFAULT '00:00',
            prompt_text TEXT NOT NULL DEFAULT '',
            description TEXT NOT NULL DEFAULT '',
            is_enabled INTEGER NOT NULL DEFAULT 1,
            run_state TEXT NOT NULL DEFAULT 'idle',
            last_run_at TEXT NOT NULL DEFAULT '',
            last_run_status TEXT NOT NULL DEFAULT '',
            last_run_message TEXT NOT NULL DEFAULT '',
            next_run_at TEXT NOT NULL DEFAULT '',
            locked_at TEXT NOT NULL DEFAULT '',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            notify_bot_key TEXT NOT NULL DEFAULT ''
        );

        CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_next_run
            ON scheduled_tasks(next_run_at);

        CREATE INDEX IF NOT EXISTS idx_scheduled_tasks_scope
            ON scheduled_tasks(task_scope);

        CREATE TABLE IF NOT EXISTS bot_config (
            bot_key TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            bot_id TEXT NOT NULL,
            secret TEXT NOT NULL,
            bind_status TEXT NOT NULL DEFAULT 'unbound',
            bound_user_id TEXT NOT NULL DEFAULT '',
            bound_chat_id TEXT NOT NULL DEFAULT '',
            agent_provider TEXT NOT NULL DEFAULT '',
            system_prompt TEXT NOT NULL DEFAULT '',
            startup_text TEXT NOT NULL DEFAULT '',
            shutdown_text TEXT NOT NULL DEFAULT '',
            is_active INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            deleted_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS mcp_tool_catalog (
            id TEXT PRIMARY KEY,
            server_name TEXT NOT NULL,
            tool_name TEXT NOT NULL,
            description TEXT NOT NULL DEFAULT '',
            enabled INTEGER NOT NULL DEFAULT 1,
            last_seen_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE TABLE IF NOT EXISTS mcp_server_config (
            server_id TEXT PRIMARY KEY,
            name TEXT NOT NULL,
            server_type TEXT NOT NULL,
            config_json TEXT NOT NULL,
            tools_json TEXT NOT NULL DEFAULT '[]',
            is_active INTEGER NOT NULL DEFAULT 0,
            scope TEXT NOT NULL DEFAULT 'bot',
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE TABLE IF NOT EXISTS bot_skill_mapping (
            bot_key TEXT NOT NULL,
            skill_name TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (bot_key, skill_name)
        );

        CREATE TABLE IF NOT EXISTS bot_mcp_mapping (
            bot_key TEXT NOT NULL,
            server_id TEXT NOT NULL,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL,
            PRIMARY KEY (bot_key, server_id)
        );

        CREATE TABLE IF NOT EXISTS token_usage (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            provider_key TEXT NOT NULL DEFAULT '',
            provider_type TEXT NOT NULL DEFAULT '',
            model TEXT NOT NULL DEFAULT '',
            call_type TEXT NOT NULL DEFAULT 'answer',
            chat_id TEXT NOT NULL DEFAULT '',
            bot_key TEXT NOT NULL DEFAULT '',
            trace_id TEXT NOT NULL DEFAULT '',
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0
        );

        CREATE INDEX IF NOT EXISTS idx_token_usage_created
            ON token_usage(created_at);

        CREATE INDEX IF NOT EXISTS idx_token_usage_provider
            ON token_usage(provider_key);

        CREATE INDEX IF NOT EXISTS idx_token_usage_bot
            ON token_usage(bot_key);

        CREATE INDEX IF NOT EXISTS idx_token_usage_call_type
            ON token_usage(call_type);

        CREATE TABLE IF NOT EXISTS llm_request_slots (
            slot_id TEXT PRIMARY KEY,
            slot_type TEXT NOT NULL,
            trace_id TEXT NOT NULL DEFAULT '',
            acquired_at TEXT NOT NULL DEFAULT ''
        );

        CREATE TABLE IF NOT EXISTS memory_usage_audits (
            id TEXT PRIMARY KEY,
            trace_id TEXT NOT NULL,
            chat_id TEXT NOT NULL DEFAULT '',
            bot_key TEXT NOT NULL DEFAULT '',
            call_type TEXT NOT NULL DEFAULT '',
            status TEXT NOT NULL DEFAULT '',
            user_query TEXT NOT NULL DEFAULT '',
            memory_pack TEXT NOT NULL DEFAULT '',
            selected_files_json TEXT NOT NULL DEFAULT '[]',
            selected_sections_json TEXT NOT NULL DEFAULT '[]',
            omitted_files_json TEXT NOT NULL DEFAULT '[]',
            token_budget_used_estimate INTEGER NOT NULL DEFAULT 0,
            confidence TEXT NOT NULL DEFAULT '',
            needs_more_memory INTEGER NOT NULL DEFAULT 0,
            reason TEXT NOT NULL DEFAULT '',
            final_answer TEXT NOT NULL DEFAULT '',
            input_tokens INTEGER NOT NULL DEFAULT 0,
            output_tokens INTEGER NOT NULL DEFAULT 0,
            total_tokens INTEGER NOT NULL DEFAULT 0,
            created_at TEXT NOT NULL,
            updated_at TEXT NOT NULL
        );

        CREATE INDEX IF NOT EXISTS idx_memory_usage_audits_trace
            ON memory_usage_audits(trace_id);

        CREATE INDEX IF NOT EXISTS idx_memory_usage_audits_chat
            ON memory_usage_audits(chat_id);

        CREATE INDEX IF NOT EXISTS idx_memory_usage_audits_call_type
            ON memory_usage_audits(call_type);

        CREATE INDEX IF NOT EXISTS idx_memory_usage_audits_created
            ON memory_usage_audits(created_at);

        CREATE TABLE IF NOT EXISTS message_feedbacks (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            msg_id TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            bot_key TEXT NOT NULL DEFAULT '',
            user_id TEXT NOT NULL DEFAULT '',
            result TEXT NOT NULL,
            reason TEXT NOT NULL DEFAULT '',
            reviewed_at TEXT NOT NULL DEFAULT '',
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_message_feedbacks_msg
            ON message_feedbacks(msg_id);

        CREATE INDEX IF NOT EXISTS idx_message_feedbacks_chat
            ON message_feedbacks(chat_id, created_at);

        CREATE INDEX IF NOT EXISTS idx_message_feedbacks_result
            ON message_feedbacks(result, created_at);

        CREATE INDEX IF NOT EXISTS idx_message_feedbacks_reviewed
            ON message_feedbacks(result, reviewed_at, created_at);

        CREATE TABLE IF NOT EXISTS feedback_alert_log (
            id TEXT PRIMARY KEY,
            created_at TEXT NOT NULL,
            chat_id TEXT NOT NULL,
            bot_key TEXT NOT NULL DEFAULT '',
            alert_type TEXT NOT NULL DEFAULT 'useless_spike',
            threshold INTEGER NOT NULL,
            window_minutes INTEGER NOT NULL,
            feedback_count INTEGER NOT NULL,
            notified_at TEXT NOT NULL,
            metadata_json TEXT NOT NULL DEFAULT '{}'
        );

        CREATE INDEX IF NOT EXISTS idx_feedback_alert_log_chat_bot
            ON feedback_alert_log(chat_id, bot_key, notified_at);

        CREATE INDEX IF NOT EXISTS idx_feedback_alert_log_created
            ON feedback_alert_log(created_at);

        """
    )

    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_bot_config_unique_active_name
            ON bot_config(name, deleted_at)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_agent_provider_config_unique_label
        ON agent_provider_config(label)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_skill_config_unique_display_name
        ON skill_config(display_name)
        """
    )
    conn.execute(
        """
        CREATE UNIQUE INDEX IF NOT EXISTS idx_mcp_server_config_unique_name
        ON mcp_server_config(name)
        """
    )
    now = _schema_now()
    conn.execute(
        """
        INSERT INTO console_users (
            username, display_name, role, password_hash,
            is_active, last_login_at, created_at, updated_at
        )
        SELECT ?, ?, ?, ?, 1, '', ?, ?
        WHERE NOT EXISTS (SELECT 1 FROM console_users WHERE username = ?)
        """,
        ("admin", "管理员", "admin", _DEFAULT_ADMIN_PASSWORD_HASH, now, now, "admin"),
    )
    conn.execute(
        """
        UPDATE console_users
        SET role = CASE WHEN username = 'admin' THEN 'admin' ELSE 'user' END
        WHERE role != CASE WHEN username = 'admin' THEN 'admin' ELSE 'user' END
        """
    )
