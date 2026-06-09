from __future__ import annotations

import base64
import hashlib
import hmac
import json
import secrets
import time
from pathlib import Path
from typing import Any


SESSION_TTL_SECONDS = 24 * 60 * 60
_SESSION_SECRET_FILENAME = "auth_session.key"
_GUEST_KICK_FILENAME = "guest_kick_counter"


class AuthTokenError(Exception):
    pass


def _base64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode("ascii")


def _base64url_decode(data: str) -> bytes:
    padding = "=" * (-len(data) % 4)
    return base64.urlsafe_b64decode((data + padding).encode("ascii"))


def _secret_path(project_root: Path) -> Path:
    return project_root.resolve() / "data" / _SESSION_SECRET_FILENAME


def get_session_secret(project_root: Path) -> bytes:
    path = _secret_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    if path.exists():
        raw = path.read_text(encoding="utf-8").strip()
        if raw:
            return bytes.fromhex(raw)
    secret = secrets.token_bytes(32)
    path.write_text(secret.hex(), encoding="utf-8")
    return secret


def _guest_kick_path(project_root: Path) -> Path:
    return project_root.resolve() / "data" / _GUEST_KICK_FILENAME


def get_guest_kick_counter(project_root: Path) -> int:
    path = _guest_kick_path(project_root)
    if path.exists():
        try:
            return int(path.read_text(encoding="utf-8").strip())
        except ValueError:
            pass
    return 0


def increment_guest_kick_counter(project_root: Path) -> int:
    path = _guest_kick_path(project_root)
    path.parent.mkdir(parents=True, exist_ok=True)
    next_val = get_guest_kick_counter(project_root) + 1
    path.write_text(str(next_val), encoding="utf-8")
    return next_val


def _config_flag_enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    if isinstance(value, int):
        return value == 1
    return False


def get_guest_account_config() -> dict[str, str] | None:
    from app.yaml_config import get_yaml_config

    guest_cfg = get_yaml_config().get("guest_account")
    if not isinstance(guest_cfg, dict) or not _config_flag_enabled(guest_cfg.get("enabled", False)):
        return None
    username = str(guest_cfg.get("username") or "").strip()
    password = str(guest_cfg.get("password") or "")
    if not username or not password:
        return None
    return {
        "username": username,
        "password": password,
    }


def create_session_id() -> str:
    return secrets.token_urlsafe(32)


def issue_session_token(
    *,
    project_root: Path,
    user: dict[str, Any],
    session_id: str,
    ttl_seconds: int = SESSION_TTL_SECONDS,
) -> dict[str, Any]:
    now = int(time.time())
    expires_at = now + int(ttl_seconds)
    payload: dict[str, Any] = {
        "sub": str(user.get("username") or ""),
        "role": str(user.get("role") or "user"),
        "sid": str(session_id or ""),
        "iat": now,
        "exp": expires_at,
        "nonce": secrets.token_urlsafe(12),
    }
    if payload["role"] == "guest":
        payload["gkv"] = get_guest_kick_counter(project_root)
    payload_bytes = json.dumps(payload, ensure_ascii=False, separators=(",", ":")).encode("utf-8")
    payload_text = _base64url_encode(payload_bytes)
    signature = hmac.new(
        get_session_secret(project_root),
        payload_text.encode("ascii"),
        hashlib.sha256,
    ).digest()
    return {
        "token": f"{payload_text}.{_base64url_encode(signature)}",
        "expires_at": expires_at,
        "expires_in": max(0, expires_at - now),
    }


def verify_session_token(*, project_root: Path, token: str) -> dict[str, Any]:
    raw_token = str(token or "").strip()
    if not raw_token or "." not in raw_token:
        raise AuthTokenError("登录已过期，请重新登录")
    payload_text, signature_text = raw_token.rsplit(".", 1)
    try:
        expected_signature = hmac.new(
            get_session_secret(project_root),
            payload_text.encode("ascii"),
            hashlib.sha256,
        ).digest()
        actual_signature = _base64url_decode(signature_text)
    except Exception as exc:
        raise AuthTokenError("登录已过期，请重新登录") from exc
    if not hmac.compare_digest(actual_signature, expected_signature):
        raise AuthTokenError("登录已过期，请重新登录")
    try:
        payload = json.loads(_base64url_decode(payload_text).decode("utf-8"))
    except Exception as exc:
        raise AuthTokenError("登录已过期，请重新登录") from exc
    expires_at = int(payload.get("exp") or 0)
    if expires_at <= int(time.time()):
        raise AuthTokenError("登录已过期，请重新登录")
    username = str(payload.get("sub") or "").strip()
    session_id = str(payload.get("sid") or "").strip()
    if not username or not session_id:
        raise AuthTokenError("登录已过期，请重新登录")
    if str(payload.get("role") or "") == "guest":
        guest_cfg = get_guest_account_config()
        if guest_cfg is None or username != guest_cfg["username"]:
            raise AuthTokenError("登录已过期，请重新登录")
        try:
            token_gkv = int(payload.get("gkv") or 0)
        except (TypeError, ValueError) as exc:
            raise AuthTokenError("登录已过期，请重新登录") from exc
        current_gkv = get_guest_kick_counter(project_root)
        if token_gkv != current_gkv:
            raise AuthTokenError("登录已过期，请重新登录")
    return payload


def extract_bearer_token(authorization: str | None) -> str:
    value = str(authorization or "").strip()
    if not value:
        return ""
    prefix = "Bearer "
    if value.lower().startswith(prefix.lower()):
        return value[len(prefix):].strip()
    return ""
