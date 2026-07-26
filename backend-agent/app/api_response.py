from __future__ import annotations

import json
import logging
import re
import traceback
from dataclasses import dataclass
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode
from uuid import uuid4

from fastapi import FastAPI, HTTPException, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse, Response

from app.db.log_store import insert_project_log
from app.exceptions import AppError


_SILENT_API_PATHS = frozenset({
    "/api/project-logs",
})

_POLLING_API_PREFIXES = (
    "/api/status",
    "/api/chats",
    "/api/ai/status",
    "/api/bots",
    "/api/agents",
    "/api/data/overview",
    "/api/data/token-usage",
    "/api/skills",
    "/api/mcp/tools",
    "/api/mcp/servers",
    "/api/tasks/periodic",
    "/api/tasks/one-time",
    "/api/tasks/executors",
    "/api/documents",
    "/api/platform-settings",
    "/api/manual-replies",
)

_SECRET_PATTERNS = [
    re.compile(
        r'("?(?:api[_-]?key|secret|token|password|authorization)"?\s*:\s*")([^"]*)(")',
        re.IGNORECASE,
    ),
    re.compile(
        r"((?:api[_-]?key|secret|token|password|authorization)\s*=\s*)([^\s,;]+)",
        re.IGNORECASE,
    ),
]


@dataclass(frozen=True)
class ApiErrorResponse:
    message: str
    trace_id: str
    ok: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "ok": self.ok,
            "message": self.message,
            "trace_id": self.trace_id,
        }


class ApiError(Exception):
    def __init__(
        self,
        message: str,
        *,
        status_code: int = 400,
        trace_id: str | None = None,
        log_message: str | None = None,
        log_detail: str = "",
        log_category: str = "network",
    ) -> None:
        super().__init__(message)
        self.message = message
        self.status_code = status_code
        self.trace_id = trace_id or str(uuid4())
        self.log_message = log_message or message
        self.log_detail = log_detail
        self.log_category = log_category


def install_api_exception_handlers(
    app: FastAPI,
    *,
    database_path: Path,
    logger: logging.Logger,
) -> None:
    _polling_cache: dict[str, str] = {}

    @app.middleware("http")
    async def _trace_api_response(request: Request, call_next) -> Response:
        if not request.url.path.startswith("/api"):
            return await call_next(request)

        trace_id = str(uuid4())
        request.state.trace_id = trace_id
        # 绑定当前异步上下文的 trace_id，使请求处理过程中的所有日志
        # 自动携带同一 trace_id（由 TraceIdFilter 注入）。
        from app.logger import set_trace_id, reset_trace_id
        set_trace_id(trace_id)
        try:
            response = await call_next(request)
        finally:
            reset_trace_id()
        fallback_trace_id = str(getattr(request.state, "trace_id", trace_id))

        content_type = response.headers.get("content-type", "")
        if "application/json" not in content_type.lower():
            response.headers["X-Trace-Id"] = fallback_trace_id
            return response

        body = b""
        async for chunk in response.body_iterator:
            body += chunk

        payload = _decode_json_body(body)
        wrapped_payload = _wrap_api_payload(payload, trace_id=fallback_trace_id, status_code=response.status_code)
        current_trace_id = str(wrapped_payload["trace_id"])
        if not bool(getattr(request.state, "api_error_logged", False)):
            _persist_api_access_log(
                request=request,
                database_path=database_path,
                logger=logger,
                status_code=response.status_code,
                trace_id=current_trace_id,
                payload=wrapped_payload,
                polling_cache=_polling_cache,
            )

        headers = dict(response.headers)
        headers.pop("content-length", None)
        headers["X-Trace-Id"] = current_trace_id
        return JSONResponse(
            content=wrapped_payload,
            status_code=response.status_code,
            headers=headers,
            media_type="application/json",
        )

    @app.exception_handler(AppError)
    async def _handle_app_error(request: Request, exc: AppError) -> JSONResponse:
        return _error_response(
            request=request,
            database_path=database_path,
            logger=logger,
            status_code=exc.status_code,
            message=exc.message,
            trace_id=str(uuid4()),
            exc=exc,
            log_message=f"AppError: {exc.message}",
            extra_detail=exc.detail,
        )

    @app.exception_handler(ApiError)
    async def _handle_api_error(request: Request, exc: ApiError) -> JSONResponse:
        return _error_response(
            request=request,
            database_path=database_path,
            logger=logger,
            status_code=exc.status_code,
            message=exc.message,
            trace_id=exc.trace_id,
            exc=exc,
            log_message=exc.log_message,
            extra_detail=exc.log_detail,
            log_category=exc.log_category,
        )

    @app.exception_handler(HTTPException)
    async def _handle_http_exception(request: Request, exc: HTTPException) -> JSONResponse:
        message = _public_http_message(exc)
        return _error_response(
            request=request,
            database_path=database_path,
            logger=logger,
            status_code=exc.status_code,
            message=message,
            trace_id=str(uuid4()),
            exc=exc,
            log_message=f"HTTP {exc.status_code}: {message}",
            extra_detail=f"detail={_sanitize_text(exc.detail)}",
        )

    @app.exception_handler(RequestValidationError)
    async def _handle_validation_error(
        request: Request,
        exc: RequestValidationError,
    ) -> JSONResponse:
        return _error_response(
            request=request,
            database_path=database_path,
            logger=logger,
            status_code=422,
            message="请求参数错误",
            trace_id=str(uuid4()),
            exc=exc,
            log_message="Request validation failed",
            extra_detail=_sanitize_text(exc.errors()),
        )

    @app.exception_handler(Exception)
    async def _handle_unexpected_error(request: Request, exc: Exception) -> JSONResponse:
        return _error_response(
            request=request,
            database_path=database_path,
            logger=logger,
            status_code=500,
            message="服务内部错误",
            trace_id=str(uuid4()),
            exc=exc,
            log_message="Unhandled API exception",
        )


def _error_response(
    *,
    request: Request,
    database_path: Path,
    logger: logging.Logger,
    status_code: int,
    message: str,
    trace_id: str,
    exc: BaseException,
    log_message: str,
    extra_detail: str = "",
    log_category: str = "network",
) -> JSONResponse:
    request.state.trace_id = trace_id
    request.state.api_error_logged = True
    safe_message = _trim_public_message(_sanitize_text(message))
    safe_detail = _trim_public_message(_sanitize_text(extra_detail))
    detail = _build_log_detail(
        request=request,
        status_code=status_code,
        public_message=safe_message,
        exc=exc,
        extra_detail=extra_detail,
    )
    try:
        insert_project_log(
            database_path,
            level=_level_for_failure(status_code),
            category=log_category,
            source=f"api:{request.method} {request.url.path}",
            message=_sanitize_text(log_message, max_length=500),
            detail=detail,
            trace_id=trace_id,
            error_code=str(status_code),
        )
    except Exception:
        logger.exception(
            "Failed to persist API error log.",
            extra={"trace_id": trace_id, "category": "data"},
        )

    return JSONResponse(
        status_code=status_code,
        content=ApiErrorResponse(
            message=safe_message,
            trace_id=trace_id,
        ).to_dict(),
    )


def _public_http_message(exc: HTTPException) -> str:
    if exc.status_code >= 500:
        return "服务内部错误"
    if isinstance(exc.detail, str) and exc.detail.strip():
        return exc.detail.strip()
    return "请求处理失败"


def _decode_json_body(body: bytes) -> Any:
    if not body:
        return {}
    try:
        return json.loads(body.decode("utf-8"))
    except Exception:
        return {"data": body.decode("utf-8", errors="replace")}


def _wrap_api_payload(payload: Any, *, trace_id: str, status_code: int) -> dict[str, Any]:
    if isinstance(payload, dict):
        wrapped = dict(payload)
    else:
        wrapped = {"data": payload}

    wrapped.setdefault("ok", status_code < 400 and wrapped.get("ok") is not False)
    wrapped["trace_id"] = str(wrapped.get("trace_id") or wrapped.get("traceId") or trace_id)
    return wrapped


def _persist_api_access_log(
    *,
    request: Request,
    database_path: Path,
    logger: logging.Logger,
    status_code: int,
    trace_id: str,
    payload: dict[str, Any],
    polling_cache: dict[str, str],
) -> None:
    path = request.url.path

    if path in _SILENT_API_PATHS:
        return

    is_failed = status_code >= 400 or payload.get("ok") is False

    if request.method.upper() == "GET" and not is_failed and _is_polling_path(path):
        body_hash = _stable_payload_hash(payload)
        cached_hash = polling_cache.get(path)
        if cached_hash == body_hash:
            return
        polling_cache[path] = body_hash

    level = "INFO"
    message = "API request succeeded"
    if is_failed:
        level = _level_for_failure(status_code)
        message = "API request failed"

    detail = _build_access_log_detail(
        request=request,
        status_code=status_code,
        payload=payload,
    )
    try:
        error_code = str(status_code) if status_code >= 400 else ""
        category = _api_log_category_for_path(path)
        insert_project_log(
            database_path,
            level=level,
            category=category,
            source=f"api:{request.method} {path}",
            message=message,
            detail=detail,
            trace_id=trace_id,
            error_code=error_code,
        )
    except Exception:
        logger.exception(
            "Failed to persist API access log.",
            extra={"trace_id": trace_id, "category": "data"},
        )


def _build_access_log_detail(*, request: Request, status_code: int, payload: dict[str, Any]) -> str:
    reserved_keys = {"ok", "trace_id", "traceId", "message"}
    response_payload = {k: payload[k] for k in payload.keys() if k not in {"traceId"}}
    business_payload = {k: payload[k] for k in payload.keys() if k not in reserved_keys}
    parts = [
        f"method={request.method}",
        f"path={request.url.path}",
        f"query={_sanitize_query(request.url.query)}",
        f"status_code={status_code}",
        f"ok={payload.get('ok')}",
    ]
    parts.extend(_operator_log_parts(request))
    parts.append(f"message={payload.get('message') or '<empty>'}")
    if business_payload:
        parts.append(f"response_data={json.dumps(business_payload, ensure_ascii=False)}")
    else:
        parts.append("response_data=<empty>")
    parts.append(f"response_json={json.dumps(response_payload, ensure_ascii=False)}")
    return _sanitize_text("\n".join(parts), max_length=50000)


def _api_log_category_for_path(path: str) -> str:
    normalized = str(path or "").strip().lower()
    if normalized.startswith("/api/agents/") and normalized.endswith("/test"):
        return "ai"
    return "network"


def _is_polling_path(path: str) -> bool:
    if not path.startswith("/api/"):
        return False
    for prefix in _POLLING_API_PREFIXES:
        if path == prefix or path.startswith(prefix + "/"):
            return True
    return False


def _stable_payload_hash(payload: dict[str, Any]) -> str:
    import hashlib

    stripped = {k: v for k, v in payload.items() if k not in {"trace_id", "traceId"}}
    raw = json.dumps(stripped, sort_keys=True, ensure_ascii=False, default=str)
    return hashlib.md5(raw.encode()).hexdigest()


def _level_for_failure(status_code: int) -> str:
    if status_code >= 500:
        return "ERROR"
    return "WARNING"


def _build_log_detail(
    *,
    request: Request,
    status_code: int,
    public_message: str,
    exc: BaseException,
    extra_detail: str = "",
) -> str:
    parts = [
        f"method={request.method}",
        f"path={request.url.path}",
        f"query={_sanitize_query(request.url.query)}",
        f"status_code={status_code}",
        f"public_message={public_message}",
        f"exception_type={type(exc).__name__}",
    ]
    parts.extend(_operator_log_parts(request))
    if extra_detail:
        parts.append(f"extra={extra_detail}")
    parts.append("traceback:")
    parts.append("".join(traceback.format_exception(type(exc), exc, exc.__traceback__)))
    return _sanitize_text("\n".join(parts), max_length=20000)


def _operator_log_parts(request: Request) -> list[str]:
    user = getattr(request.state, "auth_user", None)
    if not isinstance(user, dict):
        return [
            "operator_username=<empty>",
            "operator_display_name=<empty>",
            "operator_role=<empty>",
        ]
    username = str(user.get("username") or "").strip() or "<empty>"
    display_name = str(user.get("display_name") or "").strip() or "<empty>"
    role = str(user.get("role") or "").strip() or "<empty>"
    return [
        f"operator_username={username}",
        f"operator_display_name={display_name}",
        f"operator_role={role}",
    ]


def _sanitize_text(value: Any, *, max_length: int | None = None) -> str:
    text = value if isinstance(value, str) else repr(value)
    for pattern in _SECRET_PATTERNS:
        text = pattern.sub(lambda match: f"{match.group(1)}***{match.group(3) if match.lastindex == 3 else ''}", text)
    if max_length is not None and len(text) > max_length:
        text = text[:max_length] + "..."
    return text


def _sanitize_query(query: Any) -> str:
    text = str(query or "")
    if not text:
        return ""
    try:
        pairs = parse_qsl(text, keep_blank_values=True)
    except ValueError:
        return _sanitize_text(text)
    sanitized = [
        (key, "***" if _is_secret_query_key(key) else value)
        for key, value in pairs
    ]
    return urlencode(sanitized, doseq=True)


def _is_secret_query_key(key: str) -> bool:
    normalized = str(key or "").strip().lower().replace("-", "_")
    return any(part in normalized for part in ("token", "secret", "password", "authorization", "api_key"))


def _trim_public_message(message: str) -> str:
    message = " ".join(message.split())
    if not message:
        return "请求处理失败"
    if len(message) > 180:
        return message[:180] + "..."
    return message
