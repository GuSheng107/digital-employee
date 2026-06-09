from __future__ import annotations

import json
import sqlite3
import threading
import time
from contextlib import contextmanager
from pathlib import Path
from typing import Any, Generator

from app.db.schema import _apply_schema, _clean_identifier


def _positive_int(value: Any, default: int) -> int:
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return default
    return parsed if parsed > 0 else default


_ALLOWED_TABLES = frozenset({
    "agent_provider_config", "skill_config", "user_profile",
    "conversations", "chat_messages", "conversation_context_summaries",
    "manual_reply_commands", "project_logs", "ai_work_items",
    "scheduled_tasks", "bot_config", "mcp_tool_catalog",
    "mcp_server_config", "bot_skill_mapping", "bot_mcp_mapping",
    "token_usage", "uploaded_documents", "llm_request_slots",
    "memory_usage_audits", "console_users", "message_feedbacks",
    "feedback_alert_log",
})


def _validate_table_name(table: str) -> str:
    cleaned = _clean_identifier(table)
    if cleaned not in _ALLOWED_TABLES:
        raise ValueError(f"Invalid table name: {table!r}")
    return cleaned


def _json_object(value: str) -> dict[str, Any]:
    try:
        data = json.loads(value or "{}")
    except json.JSONDecodeError:
        return {}
    return data if isinstance(data, dict) else {}


def _json_array(value: str) -> list[Any]:
    try:
        data = json.loads(value or "[]")
    except json.JSONDecodeError:
        return []
    return data if isinstance(data, list) else []


def _row_value(row: Any, key: str, default: Any = "") -> Any:
    return row[key] if key in row.keys() else default


_wal_set: dict[str, bool] = {}
_wal_lock = threading.Lock()


def _ensure_wal_mode(path: Path) -> None:
    key = str(path.resolve())
    with _wal_lock:
        if _wal_set.get(key):
            return
    try:
        conn = sqlite3.connect(str(path), timeout=30)
        conn.execute("PRAGMA journal_mode = WAL")
        conn.close()
    except Exception:
        pass
    with _wal_lock:
        _wal_set[key] = True


def _create_connection(path: Path) -> sqlite3.Connection:
    path.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(str(path), timeout=30)
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA busy_timeout = 30000")
    return conn


def is_database_locked_error(exc: BaseException) -> bool:
    return isinstance(exc, sqlite3.OperationalError) and "database is locked" in str(exc).lower()


def run_sqlite_maintenance(path: Path, *, retries: int = 3, retry_delay_seconds: float = 2.0) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    last_error: sqlite3.OperationalError | None = None
    for attempt in range(max(1, retries)):
        try:
            conn = sqlite3.connect(str(path), timeout=30, isolation_level=None)
            try:
                conn.execute("PRAGMA busy_timeout = 30000")
                conn.execute("PRAGMA wal_checkpoint(TRUNCATE)")
                conn.execute("VACUUM")
            finally:
                conn.close()
            return
        except sqlite3.OperationalError as exc:
            if not is_database_locked_error(exc):
                raise
            last_error = exc
            if attempt < max(1, retries) - 1:
                time.sleep(max(0.0, retry_delay_seconds))
    if last_error is not None:
        raise last_error


@contextmanager
def connect_database(path: Path) -> Generator[sqlite3.Connection, None, None]:
    conn = _create_connection(path)
    try:
        yield conn
    except BaseException:
        conn.rollback()
        raise
    else:
        conn.commit()
    finally:
        try:
            conn.close()
        except Exception:
            pass


_db_initialized: dict[str, bool] = {}
_db_init_lock = threading.Lock()


def initialize_database(path: Path) -> Path:
    database_path = path.resolve()
    key = str(database_path)
    with _db_init_lock:
        if not _db_initialized.get(key):
            _ensure_wal_mode(database_path)
            with connect_database(database_path) as conn:
                _apply_schema(conn)
            _db_initialized[key] = True
    return database_path


def reset_db_initialized(path: Path | None = None) -> None:
    with _db_init_lock:
        if path is None:
            _db_initialized.clear()
        else:
            key = str(path.resolve())
            _db_initialized.pop(key, None)
