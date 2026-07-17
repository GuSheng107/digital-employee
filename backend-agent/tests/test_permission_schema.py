from __future__ import annotations

import sqlite3
import tempfile
import unittest
from pathlib import Path

from app.db.core import connect_database, initialize_database, reset_db_initialized
from app.db.permission_store import role_allowed_for_route


class PermissionSchemaTest(unittest.TestCase):
    def test_permission_tables_and_guest_seed_are_initialized(self) -> None:
        db_path = Path(tempfile.mkdtemp()) / "auth.db"
        reset_db_initialized(db_path)
        initialize_database(db_path)

        with connect_database(db_path) as conn:
            tables = {
                row["name"]
                for row in conn.execute(
                    """
                    SELECT name
                    FROM sqlite_master
                    WHERE type = 'table'
                    """
                ).fetchall()
            }

        self.assertIn("auth_roles", tables)
        self.assertIn("auth_permissions", tables)
        self.assertIn("auth_user_roles", tables)
        self.assertIn("auth_role_permissions", tables)
        self.assertIn("auth_route_permissions", tables)
        self.assertIn("auth_permission_audit_logs", tables)
        self.assertTrue(
            role_allowed_for_route(
                db_path,
                role_key="guest",
                method="GET",
                path="/api/status",
            )
        )
        self.assertFalse(
            role_allowed_for_route(
                db_path,
                role_key="guest",
                method="POST",
                path="/api/auth/users",
            )
        )

    def test_legacy_caller_type_migrates_to_user_type(self) -> None:
        db_path = Path(tempfile.mkdtemp()) / "legacy.db"
        db_path.parent.mkdir(parents=True, exist_ok=True)
        conn = sqlite3.connect(str(db_path))
        try:
            conn.executescript(
                """
                CREATE TABLE console_users (
                    username TEXT PRIMARY KEY,
                    display_name TEXT NOT NULL DEFAULT '',
                    role TEXT NOT NULL,
                    password_hash TEXT NOT NULL,
                    caller_type TEXT NOT NULL DEFAULT 'external',
                    is_active INTEGER NOT NULL DEFAULT 1,
                    active_session_id TEXT NOT NULL DEFAULT '',
                    active_session_expires_at INTEGER NOT NULL DEFAULT 0,
                    last_login_at TEXT NOT NULL DEFAULT '',
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL
                );
                INSERT INTO console_users (
                    username, display_name, role, password_hash, caller_type,
                    created_at, updated_at
                )
                VALUES ('svc', 'svc', 'user', 'x', 'internal', 'now', 'now');
                """
            )
            conn.commit()
        finally:
            conn.close()

        reset_db_initialized(db_path)
        initialize_database(db_path)

        with connect_database(db_path) as migrated:
            row = migrated.execute(
                "SELECT user_type FROM console_users WHERE username = 'svc'"
            ).fetchone()

        self.assertIsNotNone(row)
        self.assertEqual(row["user_type"], "internal")


if __name__ == "__main__":
    unittest.main()
