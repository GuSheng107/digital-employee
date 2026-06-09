from __future__ import annotations

import hashlib
import hmac
import re
import secrets
import sqlite3
from pathlib import Path
from typing import Any

from app.db.core import connect_database, initialize_database
from app.exceptions import ConflictError, NotFoundError, ValidationError
from app.utils import utc_now


AUTH_TABLE = "console_users"
ADMIN_USERNAME = "admin"
_PASSWORD_ALGORITHM = "pbkdf2_sha256"
_PASSWORD_ITERATIONS = 210_000
_SALT_BYTES = 16
_PASSWORD_PATTERN = re.compile(r"^[A-Za-z0-9]+$")


def ensure_auth_schema(database_path: Path) -> None:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        conn.executescript(
            """
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
            """
        )


def auth_schema_exists(database_path: Path) -> bool:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        row = conn.execute(
            """
            SELECT name
            FROM sqlite_master
            WHERE type = 'table' AND name = ?
            """,
            (AUTH_TABLE,),
        ).fetchone()
    return row is not None


def normalize_username(username: Any) -> str:
    value = str(username or "").strip()
    if not value:
        raise ValidationError("用户名不能为空")
    if len(value) > 64:
        raise ValidationError("用户名不能超过 64 个字符")
    allowed = set("abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ0123456789._-@")
    if any(char not in allowed for char in value):
        raise ValidationError("用户名只能包含字母、数字、点、下划线、短横线和 @")
    return value


def role_for_username(username: str) -> str:
    return "admin" if str(username or "").strip() == ADMIN_USERNAME else "user"


def validate_password(password: Any) -> str:
    value = str(password or "")
    if len(value) < 8:
        raise ValidationError("密码至少需要 8 位")
    if len(value) > 256:
        raise ValidationError("密码不能超过 256 位")
    if not _PASSWORD_PATTERN.fullmatch(value):
        raise ValidationError("密码只能包含英文字母和数字")
    if not any(char.isalpha() for char in value) or not any(char.isdigit() for char in value):
        raise ValidationError("密码必须同时包含英文字母和数字")
    return value


def hash_password(password: str) -> str:
    raw_password = validate_password(password)
    salt = secrets.token_bytes(_SALT_BYTES)
    digest = hashlib.pbkdf2_hmac(
        "sha256",
        raw_password.encode("utf-8"),
        salt,
        _PASSWORD_ITERATIONS,
    )
    return "$".join(
        [
            _PASSWORD_ALGORITHM,
            str(_PASSWORD_ITERATIONS),
            salt.hex(),
            digest.hex(),
        ]
    )


def verify_password(password: str, stored_hash: str) -> bool:
    try:
        algorithm, iterations_text, salt_hex, digest_hex = str(stored_hash or "").split("$", 3)
        if algorithm != _PASSWORD_ALGORITHM:
            return False
        iterations = int(iterations_text)
        salt = bytes.fromhex(salt_hex)
        expected = bytes.fromhex(digest_hex)
    except (TypeError, ValueError):
        return False
    actual = hashlib.pbkdf2_hmac(
        "sha256",
        str(password or "").encode("utf-8"),
        salt,
        iterations,
    )
    return hmac.compare_digest(actual, expected)


def _require_schema(database_path: Path) -> None:
    if not auth_schema_exists(database_path):
        raise ValidationError("登录用户表未初始化，请重启服务后重试")


def _public_user(row: sqlite3.Row | dict[str, Any] | None) -> dict[str, Any] | None:
    if row is None:
        return None
    data = dict(row)
    username = str(data.get("username") or "")
    expires_at = int(data.get("active_session_expires_at") or 0)
    import time
    is_online = expires_at > int(time.time())
    return {
        "username": username,
        "display_name": str(data.get("display_name") or ""),
        "role": role_for_username(username),
        "is_active": bool(data.get("is_active")),
        "is_online": is_online,
        "last_login_at": str(data.get("last_login_at") or ""),
        "created_at": str(data.get("created_at") or ""),
        "updated_at": str(data.get("updated_at") or ""),
    }


def list_console_users(database_path: Path) -> list[dict[str, Any]]:
    _require_schema(database_path)
    with connect_database(database_path) as conn:
        rows = conn.execute(
            """
            SELECT username, display_name, role, is_active, active_session_expires_at,
                   last_login_at, created_at, updated_at
            FROM console_users
            ORDER BY username = 'admin' DESC, username COLLATE NOCASE
            """
        ).fetchall()
    return [item for item in (_public_user(row) for row in rows) if item is not None]


def get_console_user(database_path: Path, username: str) -> dict[str, Any] | None:
    _require_schema(database_path)
    clean_username = normalize_username(username)
    with connect_database(database_path) as conn:
        row = conn.execute(
            """
            SELECT username, display_name, role, is_active, active_session_expires_at,
                   last_login_at, created_at, updated_at
            FROM console_users
            WHERE username = ?
            """,
            (clean_username,),
        ).fetchone()
    return _public_user(row)


def get_console_user_for_auth(database_path: Path, username: str) -> dict[str, Any] | None:
    _require_schema(database_path)
    clean_username = normalize_username(username)
    with connect_database(database_path) as conn:
        row = conn.execute(
            """
            SELECT username, display_name, role, password_hash, is_active, last_login_at, created_at, updated_at
            FROM console_users
            WHERE username = ?
            """,
            (clean_username,),
        ).fetchone()
    return dict(row) if row else None


def authenticate_console_user(
    database_path: Path,
    *,
    username: str,
    password: str,
) -> dict[str, Any] | None:
    user = get_console_user_for_auth(database_path, username)
    if not user or not bool(user.get("is_active")):
        return None
    if not verify_password(str(password or ""), str(user.get("password_hash") or "")):
        return None
    return _public_user(user)


def activate_console_user_session(
    database_path: Path,
    *,
    username: str,
    session_id: str,
    expires_at: int,
) -> None:
    _require_schema(database_path)
    clean_username = normalize_username(username)
    clean_session_id = str(session_id or "").strip()
    if not clean_session_id:
        raise ValidationError("会话 ID 不能为空")
    now = utc_now()
    with connect_database(database_path) as conn:
        conn.execute(
            """
            UPDATE console_users
            SET active_session_id = ?,
                active_session_expires_at = ?,
                last_login_at = ?,
                updated_at = ?
            WHERE username = ?
            """,
            (clean_session_id, int(expires_at or 0), now, now, clean_username),
        )


def clear_console_user_session(
    database_path: Path,
    *,
    username: str,
    session_id: str = "",
) -> None:
    _require_schema(database_path)
    clean_username = normalize_username(username)
    clean_session_id = str(session_id or "").strip()
    now = utc_now()
    if clean_session_id:
        with connect_database(database_path) as conn:
            conn.execute(
                """
                UPDATE console_users
                SET active_session_id = '',
                    active_session_expires_at = 0,
                    updated_at = ?
                WHERE username = ? AND active_session_id = ?
                """,
                (now, clean_username, clean_session_id),
            )
        return
    with connect_database(database_path) as conn:
        conn.execute(
            """
            UPDATE console_users
            SET active_session_id = '',
                active_session_expires_at = 0,
                updated_at = ?
            WHERE username = ?
            """,
            (now, clean_username),
        )


def get_console_user_for_session(
    database_path: Path,
    *,
    username: str,
    session_id: str,
    now_seconds: int,
) -> dict[str, Any] | None:
    _require_schema(database_path)
    clean_username = normalize_username(username)
    clean_session_id = str(session_id or "").strip()
    if not clean_session_id:
        return None
    with connect_database(database_path) as conn:
        row = conn.execute(
            """
            SELECT username, display_name, role, is_active, active_session_expires_at,
                   last_login_at, created_at, updated_at
            FROM console_users
            WHERE username = ?
              AND is_active = 1
              AND active_session_id = ?
              AND active_session_expires_at > ?
            """,
            (clean_username, clean_session_id, int(now_seconds or 0)),
        ).fetchone()
    return _public_user(row)


def create_console_user(
    database_path: Path,
    *,
    username: str,
    password: str,
    role: str = "user",
    display_name: str = "",
) -> dict[str, Any]:
    _require_schema(database_path)
    clean_username = normalize_username(username)
    clean_role = role_for_username(clean_username)
    clean_password_hash = hash_password(validate_password(password))
    clean_display_name = str(display_name or "").strip()[:80]
    now = utc_now()
    try:
        with connect_database(database_path) as conn:
            conn.execute(
                """
                INSERT INTO console_users (
                    username, display_name, role, password_hash,
                    is_active, last_login_at, created_at, updated_at
                )
                VALUES (?, ?, ?, ?, 1, '', ?, ?)
                """,
                (clean_username, clean_display_name, clean_role, clean_password_hash, now, now),
            )
    except sqlite3.IntegrityError as exc:
        raise ConflictError("用户名已存在") from exc
    user = get_console_user(database_path, clean_username)
    if user is None:
        raise RuntimeError("创建用户失败")
    return user


def update_console_user(
    database_path: Path,
    *,
    username: str,
    role: str = "user",
    display_name: str = "",
) -> dict[str, Any]:
    _require_schema(database_path)
    clean_username = normalize_username(username)
    existing = get_console_user(database_path, clean_username)
    if existing is None:
        raise NotFoundError("用户不存在")
    clean_role = role_for_username(clean_username)
    clean_display_name = str(display_name or "").strip()[:80]
    now = utc_now()
    with connect_database(database_path) as conn:
        conn.execute(
            """
            UPDATE console_users
            SET role = ?, display_name = ?, updated_at = ?
            WHERE username = ?
            """,
            (clean_role, clean_display_name, now, clean_username),
        )
    updated = get_console_user(database_path, clean_username)
    if updated is None:
        raise RuntimeError("更新用户失败")
    return updated


def reset_console_user_password(
    database_path: Path,
    *,
    username: str,
    password: str,
) -> dict[str, Any]:
    _require_schema(database_path)
    clean_username = normalize_username(username)
    existing = get_console_user(database_path, clean_username)
    if existing is None:
        raise NotFoundError("用户不存在")
    password_hash = hash_password(validate_password(password))
    now = utc_now()
    with connect_database(database_path) as conn:
        conn.execute(
            """
            UPDATE console_users
            SET password_hash = ?,
                active_session_id = '',
                active_session_expires_at = 0,
                updated_at = ?
            WHERE username = ?
            """,
            (password_hash, now, clean_username),
        )
    updated = get_console_user(database_path, clean_username)
    if updated is None:
        raise RuntimeError("重置密码失败")
    return updated


def change_console_user_password(
    database_path: Path,
    *,
    username: str,
    current_password: str,
    new_password: str,
) -> dict[str, Any]:
    _require_schema(database_path)
    clean_username = normalize_username(username)
    existing = get_console_user_for_auth(database_path, clean_username)
    if existing is None or not bool(existing.get("is_active")):
        raise NotFoundError("用户不存在")
    if not verify_password(str(current_password or ""), str(existing.get("password_hash") or "")):
        raise ValidationError("当前密码错误")
    password_hash = hash_password(validate_password(new_password))
    now = utc_now()
    with connect_database(database_path) as conn:
        conn.execute(
            """
            UPDATE console_users
            SET password_hash = ?, updated_at = ?
            WHERE username = ?
            """,
            (password_hash, now, clean_username),
        )
    updated = get_console_user(database_path, clean_username)
    if updated is None:
        raise RuntimeError("修改密码失败")
    return updated


def delete_console_user(database_path: Path, username: str) -> None:
    _require_schema(database_path)
    clean_username = normalize_username(username)
    if clean_username == ADMIN_USERNAME:
        raise ConflictError("admin 管理员不能删除")
    existing = get_console_user(database_path, clean_username)
    if existing is None:
        raise NotFoundError("用户不存在")
    with connect_database(database_path) as conn:
        conn.execute("DELETE FROM console_users WHERE username = ?", (clean_username,))


def authenticate_guest_user(*, username: str, password: str) -> dict[str, Any] | None:
    from app.auth import get_guest_account_config

    guest_cfg = get_guest_account_config()
    if guest_cfg is None:
        return None
    guest_user = guest_cfg["username"]
    guest_pass = guest_cfg["password"]
    if username != guest_user or password != guest_pass:
        return None
    return {
        "username": guest_user,
        "display_name": "游客",
        "role": "guest",
        "is_active": True,
        "last_login_at": "",
        "created_at": "",
        "updated_at": "",
    }
