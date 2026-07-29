"""日志载荷解析与安全凭证脱敏。"""

from __future__ import annotations

import json
import re
from typing import Any

REDACTED_VALUE = "***REDACTED***"
SENSITIVE_KEY_PARTS = frozenset(
    {
        "password",
        "password_hash",
        "access_token",
        "refresh_token",
        "captcha_answer",
        "captcha_solution",
        "captcha_image",
        "image_data_url",
        "authorization",
        "cookie",
        "api_key",
        "apikey",
        "app_secret",
        "bot_secret",
        "client_secret",
        "private_key",
        "redis_url",
        "database_url",
    }
)
TEXT_SECRET_PATTERNS = (
    re.compile(r"(?i)(bearer\s+)[^\s\"']+"),
    re.compile(
        r'(?i)(["\']?(?:password|access_token|refresh_token|captcha_answer|api_key|app_secret)'
        r'["\']?\s*[:=]\s*["\']?)[^"\'\s,}]+'
    ),
)


def is_sensitive_key(key: str) -> bool:
    """判断字段名是否属于凭证字段。"""
    normalized = key.strip().lower().replace("-", "_")
    return any(part in normalized for part in SENSITIVE_KEY_PARTS)


def sanitize_value(value: Any, *, key: str | None = None) -> Any:
    """递归保留业务信息，只移除安全凭证。"""
    if key is not None and is_sensitive_key(key):
        return REDACTED_VALUE
    if isinstance(value, dict):
        return {
            str(item_key): sanitize_value(item_value, key=str(item_key))
            for item_key, item_value in value.items()
        }
    if isinstance(value, list):
        return [sanitize_value(item) for item in value]
    if isinstance(value, tuple):
        return [sanitize_value(item) for item in value]
    if isinstance(value, str):
        sanitized = value
        for pattern in TEXT_SECRET_PATTERNS:
            sanitized = pattern.sub(rf"\1{REDACTED_VALUE}", sanitized)
        return sanitized
    return value


def sanitize_headers(headers: dict[str, str]) -> dict[str, str]:
    """脱敏请求或响应头。"""
    return {
        key: REDACTED_VALUE if is_sensitive_key(key) else value
        for key, value in headers.items()
    }


def decode_body(body: bytes, content_type: str) -> Any:
    """解析正文；文本与 JSON 完整保留，二进制只记录元数据。"""
    if not body:
        return None
    normalized_type = content_type.lower()
    if "application/json" in normalized_type:
        try:
            return sanitize_value(json.loads(body))
        except (UnicodeDecodeError, json.JSONDecodeError):
            pass
    if (
        normalized_type.startswith("text/")
        or "xml" in normalized_type
        or "x-www-form-urlencoded" in normalized_type
    ):
        return sanitize_value(body.decode("utf-8", errors="replace"))
    if "multipart/form-data" in normalized_type:
        text = body.decode("utf-8", errors="replace")
        filenames = re.findall(r'filename="([^"]+)"', text)
        fields = re.findall(r'name="([^"]+)"', text)
        return {
            "fields": fields,
            "filenames": filenames,
            "binary_omitted": True,
            "size_bytes": len(body),
        }
    return {
        "binary_omitted": True,
        "content_type": content_type or "application/octet-stream",
        "size_bytes": len(body),
    }
