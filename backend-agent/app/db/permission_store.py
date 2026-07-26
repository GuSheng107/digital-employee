from __future__ import annotations

import re
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.db.core import connect_database, initialize_database
from app.utils import utc_now


def _route_regex(pattern: str) -> re.Pattern[str]:
    escaped = re.escape(pattern.strip())
    escaped = re.sub(r"\\\{[^/]+\\\}", r"[^/]+", escaped)
    return re.compile(f"^{escaped}$")


def _route_matches(pattern: str, path: str) -> bool:
    return bool(_route_regex(pattern).match(path))


def role_allowed_for_route(
    database_path: Path,
    *,
    role_key: str,
    method: str,
    path: str,
) -> bool:
    initialize_database(database_path)
    clean_role = str(role_key or "").strip().lower()
    clean_method = str(method or "").strip().upper()
    clean_path = str(path or "").strip()
    if not clean_role or not clean_method or not clean_path:
        return False

    with connect_database(database_path) as conn:
        rows = conn.execute(
            """
            SELECT rp.method, rp.path_pattern
            FROM auth_route_permissions rp
            JOIN auth_role_permissions rperm
              ON rperm.permission_key = rp.permission_key
            WHERE rperm.role_key = ?
              AND rp.method IN (?, '*')
            """,
            (clean_role, clean_method),
        ).fetchall()

    return any(_route_matches(str(row["path_pattern"]), clean_path) for row in rows)


def insert_permission_audit_log(
    database_path: Path,
    *,
    trace_id: str,
    username: str,
    role_key: str,
    permission_key: str,
    method: str,
    path: str,
    decision: str,
    reason: str = "",
) -> None:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        conn.execute(
            """
            INSERT INTO auth_permission_audit_logs (
                id, trace_id, username, role_key, permission_key,
                method, path, decision, reason, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                str(uuid4()),
                str(trace_id or ""),
                str(username or ""),
                str(role_key or ""),
                str(permission_key or ""),
                str(method or "").upper(),
                str(path or ""),
                str(decision or ""),
                str(reason or ""),
                utc_now(),
            ),
        )


def route_permission_for_path(database_path: Path, *, method: str, path: str) -> str:
    initialize_database(database_path)
    clean_method = str(method or "").strip().upper()
    clean_path = str(path or "").strip()
    with connect_database(database_path) as conn:
        rows = conn.execute(
            """
            SELECT method, path_pattern, permission_key
            FROM auth_route_permissions
            WHERE method IN (?, '*')
            """,
            (clean_method,),
        ).fetchall()
    for row in rows:
        if _route_matches(str(row["path_pattern"]), clean_path):
            return str(row["permission_key"] or "")
    return ""
