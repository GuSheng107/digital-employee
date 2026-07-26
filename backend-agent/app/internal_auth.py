from __future__ import annotations

import hashlib
import hmac
import ipaddress
import time
from collections.abc import Mapping
from typing import Any


CALLER_ID_HEADER = "x-caller-id"
CALLER_TIMESTAMP_HEADER = "x-caller-timestamp"
CALLER_SIGNATURE_HEADER = "x-caller-signature"
CALLER_BODY_HASH_HEADER = "x-caller-body-sha256"
DEFAULT_TIMESTAMP_SKEW_SECONDS = 300
_BODY_SIGNED_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


class InternalAuthError(Exception):
    def __init__(self, message: str, status_code: int = 403) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code


def verify_internal_request(
    *,
    config: dict[str, Any],
    method: str,
    path: str,
    headers: Mapping[str, str],
    client_host: str | None,
    body: bytes = b"",
    now: int | None = None,
    max_skew_seconds: int = DEFAULT_TIMESTAMP_SKEW_SECONDS,
) -> str | None:
    preflight = verify_internal_request_metadata(
        config=config,
        method=method,
        path=path,
        headers=headers,
        client_host=client_host,
        now=now,
        max_skew_seconds=max_skew_seconds,
    )
    if preflight is None:
        return None

    normalized_headers = {str(k).lower(): str(v).strip() for k, v in headers.items()}
    caller_id = normalized_headers.get(CALLER_ID_HEADER, "")
    timestamp_text = normalized_headers.get(CALLER_TIMESTAMP_HEADER, "")
    signature = normalized_headers.get(CALLER_SIGNATURE_HEADER, "")
    body_hash = normalized_headers.get(CALLER_BODY_HASH_HEADER, "")

    callers = _internal_callers(config)
    caller_cfg = callers.get(caller_id)
    shared_secret = str(caller_cfg.get("shared_secret") or "")
    timestamp = int(timestamp_text)

    clean_method = method.upper()
    if clean_method in _BODY_SIGNED_METHODS:
        expected_body_hash = hashlib.sha256(body or b"").hexdigest()
        if not body_hash:
            raise InternalAuthError("internal caller body hash is required")
        if not hmac.compare_digest(body_hash.lower(), expected_body_hash):
            raise InternalAuthError("internal caller body hash is invalid")
        expected = _signature(shared_secret, clean_method, path, timestamp, body_hash=expected_body_hash)
    else:
        expected = _signature(shared_secret, clean_method, path, timestamp)
    if not hmac.compare_digest(signature.lower(), expected):
        raise InternalAuthError("internal caller signature is invalid")

    return caller_id


def verify_internal_request_metadata(
    *,
    config: dict[str, Any],
    method: str,
    path: str,
    headers: Mapping[str, str],
    client_host: str | None,
    now: int | None = None,
    max_skew_seconds: int = DEFAULT_TIMESTAMP_SKEW_SECONDS,
) -> str | None:
    """Validate cheap internal auth metadata before any request body is read."""
    normalized_headers = {str(k).lower(): str(v).strip() for k, v in headers.items()}
    caller_id = normalized_headers.get(CALLER_ID_HEADER, "")
    timestamp_text = normalized_headers.get(CALLER_TIMESTAMP_HEADER, "")
    signature = normalized_headers.get(CALLER_SIGNATURE_HEADER, "")

    if not caller_id and not timestamp_text and not signature:
        return None
    if not caller_id or not timestamp_text or not signature:
        raise InternalAuthError("internal caller headers are incomplete")
    if not _looks_like_sha256_hex(signature):
        raise InternalAuthError("internal caller signature is invalid")

    callers = _internal_callers(config)
    caller_cfg = callers.get(caller_id)
    if not isinstance(caller_cfg, dict):
        raise InternalAuthError("internal caller is not allowed")

    shared_secret = str(caller_cfg.get("shared_secret") or "")
    if not shared_secret:
        raise InternalAuthError("internal caller secret is not configured")

    try:
        timestamp = int(timestamp_text)
    except ValueError as exc:
        raise InternalAuthError("internal caller timestamp is invalid") from exc

    current_time = int(time.time()) if now is None else int(now)
    if abs(current_time - timestamp) > max_skew_seconds:
        raise InternalAuthError("internal caller timestamp is expired")

    if not _ip_allowed(client_host, caller_cfg.get("ip_allowlist")):
        raise InternalAuthError("internal caller IP is not allowed")

    return caller_id


def _internal_callers(config: dict[str, Any]) -> dict[str, Any]:
    direct = config.get("internal_callers")
    if isinstance(direct, dict):
        return direct
    auth_cfg = config.get("auth")
    if isinstance(auth_cfg, dict) and isinstance(auth_cfg.get("internal_callers"), dict):
        return auth_cfg["internal_callers"]
    return {}


def _signature(
    shared_secret: str,
    method: str,
    path: str,
    timestamp: int,
    *,
    body_hash: str | None = None,
) -> str:
    message = f"{method.upper()}\n{path}\n{timestamp}"
    if body_hash is not None:
        message = f"{message}\n{body_hash}"
    return hmac.new(
        shared_secret.encode("utf-8"),
        message.encode("utf-8"),
        hashlib.sha256,
    ).hexdigest()


def _looks_like_sha256_hex(value: str) -> bool:
    text = str(value or "").strip()
    if len(text) != 64:
        return False
    return all(char in "0123456789abcdefABCDEF" for char in text)


def _ip_allowed(client_host: str | None, allowlist: Any) -> bool:
    if not allowlist:
        return True
    if not client_host:
        return False
    host = client_host
    if host.startswith("::ffff:"):
        host = host[len("::ffff:"):]
    try:
        client_ip = ipaddress.ip_address(host)
    except ValueError:
        return False
    items = allowlist if isinstance(allowlist, (list, tuple)) else [allowlist]
    for item in items:
        try:
            if client_ip in ipaddress.ip_network(str(item), strict=False):
                return True
        except ValueError:
            continue
    return False
