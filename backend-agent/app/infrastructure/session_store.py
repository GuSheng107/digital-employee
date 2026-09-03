from __future__ import annotations

import json
import sqlite3
import threading
from datetime import UTC, datetime
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.core.contracts import ChatMessage, SessionStore


class SQLiteSessionStore:
    """Small SQLite implementation of the session persistence contract."""

    def __init__(self, database_path: Path) -> None:
        self.database_path = database_path
        self.database_path.parent.mkdir(parents=True, exist_ok=True)
        self._lock = threading.RLock()
        self._connection = sqlite3.connect(self.database_path, check_same_thread=False)
        self._connection.row_factory = sqlite3.Row
        self._connection.execute("PRAGMA foreign_keys = ON")
        self._initialize()

    def close(self) -> None:
        with self._lock:
            self._connection.close()

    def ensure_session(
        self,
        session_id: str | None,
        *,
        user_id: str | None = None,
        user_role: str | None = None,
    ) -> tuple[str, bool]:
        actual_id = session_id or str(uuid4())
        now = _now()
        with self._transaction() as connection:
            row = connection.execute("SELECT id FROM sessions WHERE id = ?", (actual_id,)).fetchone()
            if row is not None:
                connection.execute(
                    "UPDATE sessions SET user_id = COALESCE(user_id, ?), user_role = COALESCE(user_role, ?), updated_at = ? WHERE id = ?",
                    (user_id, user_role, now, actual_id),
                )
                return actual_id, False
            connection.execute(
                "INSERT INTO sessions (id, user_id, user_role, title, status, metadata, created_at, updated_at) VALUES (?, ?, ?, ?, 'active', ?, ?, ?)",
                (actual_id, user_id, user_role, None, "{}", now, now),
            )
            self._insert_event(connection, actual_id, "session.created", {"session_id": actual_id})
            return actual_id, True

    def load_messages(self, session_id: str) -> list[ChatMessage]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT role, content, tool_call_id, tool_calls FROM messages WHERE session_id = ? ORDER BY sequence ASC",
                (session_id,),
            ).fetchall()
        return [
            ChatMessage(
                role=row["role"],
                content=row["content"],
                tool_call_id=row["tool_call_id"],
                tool_calls=[_tool_call_from_json(item) for item in json.loads(row["tool_calls"] or "[]")],
            )
            for row in rows
        ]

    def load_events(self, session_id: str) -> list[dict[str, Any]]:
        with self._lock:
            rows = self._connection.execute(
                "SELECT id, turn_id, run_id, sequence, event_type, payload, created_at FROM events WHERE session_id = ? ORDER BY sequence ASC",
                (session_id,),
            ).fetchall()
        return [
            {
                "id": row["id"],
                "turn_id": row["turn_id"],
                "run_id": row["run_id"],
                "sequence": row["sequence"],
                "type": row["event_type"],
                "payload": json.loads(row["payload"]),
                "created_at": row["created_at"],
            }
            for row in rows
        ]

    def begin_turn(self, session_id: str, run_id: str, agent_id: str) -> str:
        turn_id = str(uuid4())
        now = _now()
        with self._transaction() as connection:
            next_sequence = self._next_sequence(connection, "turns", session_id)
            connection.execute(
                "INSERT INTO turns (id, session_id, sequence, status, started_at, metadata) VALUES (?, ?, ?, 'running', ?, ?)",
                (turn_id, session_id, next_sequence, now, "{}"),
            )
            connection.execute(
                "INSERT INTO runs (id, session_id, turn_id, parent_run_id, agent_id, status, started_at, metadata) VALUES (?, ?, ?, NULL, ?, 'running', ?, ?)",
                (run_id, session_id, turn_id, agent_id, now, "{}"),
            )
            self._insert_event(connection, session_id, "turn.started", {"turn_id": turn_id}, turn_id=turn_id, run_id=run_id)
            self._insert_event(connection, session_id, "run.started", {"run_id": run_id, "agent_id": agent_id}, turn_id=turn_id, run_id=run_id)
        return turn_id

    def append_event(
        self,
        session_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        turn_id: str | None = None,
        run_id: str | None = None,
    ) -> str:
        with self._transaction() as connection:
            event_id = self._insert_event(connection, session_id, event_type, payload, turn_id=turn_id, run_id=run_id)
            connection.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (_now(), session_id))
            return event_id

    def append_message_event(
        self,
        session_id: str,
        message: ChatMessage,
        *,
        event_type: str,
        payload: dict[str, Any],
        turn_id: str,
        run_id: str,
    ) -> str:
        with self._transaction() as connection:
            event_id = self._insert_event(connection, session_id, event_type, payload, turn_id=turn_id, run_id=run_id)
            sequence = self._next_sequence(connection, "messages", session_id)
            connection.execute(
                "INSERT INTO messages (id, session_id, turn_id, run_id, event_id, sequence, role, content, tool_call_id, tool_name, tool_calls, is_visible, metadata, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, 1, ?, ?)",
                (
                    str(uuid4()),
                    session_id,
                    turn_id,
                    run_id,
                    event_id,
                    sequence,
                    message.role,
                    message.content,
                    message.tool_call_id,
                    message.tool_calls[0].name if message.tool_calls else None,
                    json.dumps([call.model_dump(mode="json") for call in message.tool_calls], ensure_ascii=False),
                    "{}",
                    _now(),
                ),
            )
            connection.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (_now(), session_id))
            return event_id

    def finish_run(self, run_id: str, status: str) -> None:
        now = _now()
        with self._transaction() as connection:
            row = connection.execute("SELECT session_id, turn_id FROM runs WHERE id = ?", (run_id,)).fetchone()
            if row is None:
                return
            connection.execute("UPDATE runs SET status = ?, completed_at = ? WHERE id = ?", (status, now, run_id))
            connection.execute("UPDATE turns SET status = ?, completed_at = ? WHERE id = ?", (status, now, row["turn_id"]))
            connection.execute("UPDATE sessions SET updated_at = ? WHERE id = ?", (now, row["session_id"]))
            self._insert_event(connection, row["session_id"], f"run.{status}", {"run_id": run_id, "status": status}, turn_id=row["turn_id"], run_id=run_id)
            self._insert_event(connection, row["session_id"], f"turn.{status}", {"turn_id": row["turn_id"], "status": status}, turn_id=row["turn_id"], run_id=run_id)

    def get_session(self, session_id: str) -> dict[str, Any] | None:
        with self._lock:
            session = self._connection.execute("SELECT * FROM sessions WHERE id = ?", (session_id,)).fetchone()
            if session is None:
                return None
            turns = self._connection.execute("SELECT * FROM turns WHERE session_id = ? ORDER BY sequence ASC", (session_id,)).fetchall()
        return {
            "id": session["id"],
            "user_id": session["user_id"],
            "user_role": session["user_role"],
            "title": session["title"],
            "status": session["status"],
            "created_at": session["created_at"],
            "updated_at": session["updated_at"],
            "turns": [dict(turn) for turn in turns],
            "events": self.load_events(session_id),
            "messages": [message.model_dump(mode="json") for message in self.load_messages(session_id)],
        }

    def list_sessions(self, *, user_id: str | None = None, limit: int = 50) -> list[dict[str, Any]]:
        """Return small session summaries for a session picker."""
        bounded_limit = max(1, min(limit, 200))
        with self._lock:
            if user_id is None:
                rows = self._connection.execute(
                    """
                    SELECT s.id, s.user_id, s.user_role, s.status, s.created_at, s.updated_at,
                           (SELECT m.content FROM messages m
                            WHERE m.session_id = s.id AND m.role = 'user'
                            ORDER BY m.sequence ASC LIMIT 1) AS first_message,
                           (SELECT m.created_at FROM messages m
                            WHERE m.session_id = s.id AND m.role = 'user'
                            ORDER BY m.sequence ASC LIMIT 1) AS first_message_at
                    FROM sessions s
                    ORDER BY s.updated_at DESC
                    LIMIT ?
                    """,
                    (bounded_limit,),
                ).fetchall()
            else:
                rows = self._connection.execute(
                    """
                    SELECT s.id, s.user_id, s.user_role, s.status, s.created_at, s.updated_at,
                           (SELECT m.content FROM messages m
                            WHERE m.session_id = s.id AND m.role = 'user'
                            ORDER BY m.sequence ASC LIMIT 1) AS first_message,
                           (SELECT m.created_at FROM messages m
                            WHERE m.session_id = s.id AND m.role = 'user'
                            ORDER BY m.sequence ASC LIMIT 1) AS first_message_at
                    FROM sessions s
                    WHERE s.user_id = ?
                    ORDER BY s.updated_at DESC
                    LIMIT ?
                    """,
                    (user_id, bounded_limit),
                ).fetchall()
        return [dict(row) for row in rows]

    def _initialize(self) -> None:
        with self._transaction() as connection:
            connection.executescript(
                """
                CREATE TABLE IF NOT EXISTS sessions (
                    id TEXT PRIMARY KEY,
                    user_id TEXT,
                    user_role TEXT,
                    title TEXT,
                    status TEXT NOT NULL DEFAULT 'active',
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS turns (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id),
                    sequence INTEGER NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    UNIQUE(session_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS runs (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id),
                    turn_id TEXT NOT NULL REFERENCES turns(id),
                    parent_run_id TEXT,
                    agent_id TEXT NOT NULL,
                    status TEXT NOT NULL,
                    started_at TEXT NOT NULL,
                    completed_at TEXT,
                    metadata TEXT NOT NULL DEFAULT '{}'
                );
                CREATE TABLE IF NOT EXISTS events (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id),
                    turn_id TEXT,
                    run_id TEXT,
                    sequence INTEGER NOT NULL,
                    event_type TEXT NOT NULL,
                    parent_event_id TEXT,
                    payload TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    UNIQUE(session_id, sequence)
                );
                CREATE TABLE IF NOT EXISTS messages (
                    id TEXT PRIMARY KEY,
                    session_id TEXT NOT NULL REFERENCES sessions(id),
                    turn_id TEXT,
                    run_id TEXT,
                    event_id TEXT NOT NULL REFERENCES events(id),
                    sequence INTEGER NOT NULL,
                    role TEXT NOT NULL,
                    content TEXT NOT NULL,
                    tool_call_id TEXT,
                    tool_name TEXT,
                    tool_calls TEXT NOT NULL DEFAULT '[]',
                    is_visible INTEGER NOT NULL DEFAULT 1,
                    metadata TEXT NOT NULL DEFAULT '{}',
                    created_at TEXT NOT NULL,
                    UNIQUE(session_id, sequence)
                );
                CREATE INDEX IF NOT EXISTS idx_turns_session_sequence ON turns(session_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_runs_turn ON runs(turn_id);
                CREATE INDEX IF NOT EXISTS idx_events_session_sequence ON events(session_id, sequence);
                CREATE INDEX IF NOT EXISTS idx_messages_session_sequence ON messages(session_id, sequence);
                """
            )

    def _insert_event(
        self,
        connection: sqlite3.Connection,
        session_id: str,
        event_type: str,
        payload: dict[str, Any],
        *,
        turn_id: str | None = None,
        run_id: str | None = None,
    ) -> str:
        event_id = str(uuid4())
        sequence = self._next_sequence(connection, "events", session_id)
        connection.execute(
            "INSERT INTO events (id, session_id, turn_id, run_id, sequence, event_type, payload, created_at) VALUES (?, ?, ?, ?, ?, ?, ?, ?)",
            (event_id, session_id, turn_id, run_id, sequence, event_type, json.dumps(payload, ensure_ascii=False), _now()),
        )
        return event_id

    @staticmethod
    def _next_sequence(connection: sqlite3.Connection, table: str, session_id: str) -> int:
        row = connection.execute(f"SELECT COALESCE(MAX(sequence), 0) + 1 AS next_sequence FROM {table} WHERE session_id = ?", (session_id,)).fetchone()
        return int(row["next_sequence"])

    class _Transaction:
        def __init__(self, owner: "SQLiteSessionStore") -> None:
            self.owner = owner
            self.connection = owner._connection

        def __enter__(self) -> sqlite3.Connection:
            self.owner._lock.acquire()
            self.connection.execute("BEGIN")
            return self.connection

        def __exit__(self, exc_type: object, exc: object, traceback: object) -> None:
            try:
                if exc_type is None:
                    self.connection.commit()
                else:
                    self.connection.rollback()
            finally:
                self.owner._lock.release()

    def _transaction(self) -> "SQLiteSessionStore._Transaction":
        return self._Transaction(self)


def _now() -> str:
    return datetime.now(UTC).isoformat()


def _tool_call_from_json(value: dict[str, Any]):
    from app.core.contracts import ToolCall

    return ToolCall.model_validate(value)
