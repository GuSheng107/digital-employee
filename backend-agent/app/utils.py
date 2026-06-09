from __future__ import annotations

from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

DATABASE_FILENAME = "ai_database.db"

CST = timezone(timedelta(hours=8))


def default_database_path(project_root: Path | None = None) -> Path:
    root = project_root or Path.cwd()
    return root / "data" / DATABASE_FILENAME


def utc_now() -> str:
    return datetime.now(CST).isoformat()


def utc_now_minus_days(days: int) -> str:
    return (datetime.now(CST) - timedelta(days=days)).isoformat()


def utc_now_minus_seconds(seconds: int) -> str:
    return (datetime.now(CST) - timedelta(seconds=seconds)).isoformat()


def utc_last_hour() -> str:
    """获取上一个整点时间"""
    now = datetime.now(CST)
    last_hour = now.replace(minute=0, second=0, microsecond=0)
    return last_hour.isoformat()


def resolve_database_path(database_path: Path | None) -> Path:
    if database_path is not None:
        return database_path
    return default_database_path()


def extract_error_info(exc: Exception) -> dict[str, Any]:
    info: dict[str, Any] = {
        "exception_type": type(exc).__name__,
        "message": str(exc),
    }
    if hasattr(exc, "response"):
        response = exc.response
        if hasattr(response, "status_code"):
            info["status_code"] = response.status_code
        if hasattr(response, "text"):
            info["response_text"] = response.text[:500]
    for attr in ("code", "status", "error_code", "status_code"):
        if hasattr(exc, attr) and attr not in info:
            info[attr] = getattr(exc, attr)
    return info


def format_error_message(error_info: dict[str, Any]) -> str:
    parts: list[str] = []
    if "request_info" in error_info:
        req = error_info["request_info"]
        parts.append(f"请求参数: type={req.get('provider_type')}, model={req.get('model')}")
        if req.get("base_url"):
            parts.append(f"base_url={req.get('base_url')}")
    if "exception_type" in error_info:
        parts.append(f"错误类型: {error_info['exception_type']}")
    if "status_code" in error_info:
        parts.append(f"HTTP状态码: {error_info['status_code']}")
    if "message" in error_info:
        parts.append(f"错误信息: {error_info['message']}")
    if "response_text" in error_info:
        parts.append(f"API响应: {error_info['response_text']}")
    return " | ".join(parts)
