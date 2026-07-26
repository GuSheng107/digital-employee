from __future__ import annotations

"""API auth middleware.

Priority:
  1. Internal caller headers: X-Caller-ID/Timestamp/Signature.
  2. Redis opaque access token from Authorization: Bearer.
  3. Missing or invalid auth returns 401/403.

所有认证失败均携带当前请求的 trace_id（由外层 _trace_api_response 中间件注入
到 request.state.trace_id），并落库一条 WARNING 级别日志，便于全链路追踪。
"""

import ipaddress
import asyncio
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.auth import (
    DualTokenError,
    extract_bearer_token,
    get_dual_token_manager,
    validate_access_token,
)
from app.db.auth_store import get_console_user
from app.db.log_store import insert_project_log
from app.db.permission_store import (
    insert_permission_audit_log,
    role_allowed_for_route,
    route_permission_for_path,
)
from app.exceptions import AppError
from app.internal_auth import (
    InternalAuthError,
    verify_internal_request,
    verify_internal_request_metadata,
)
from app.logger import get_logger
from app.yaml_config import get_yaml_config

_PUBLIC_API_PATHS = frozenset({
    "/api/auth/login",
    "/api/auth/refresh",
})
_INTERNAL_BODY_SIGNED_METHODS = frozenset({"POST", "PUT", "PATCH", "DELETE"})
_DEFAULT_INTERNAL_MAX_BODY_BYTES = 1024 * 1024

_logger = get_logger("auth_middleware")


def _trace_id(request: Request) -> str:
    return str(getattr(request.state, "trace_id", "") or "")


async def _auth_error(request: Request, message: str, *, status_code: int = 401) -> JSONResponse:
    trace_id = _trace_id(request)
    # 认证失败落库，trace_id 贯穿全链路
    try:
        await asyncio.to_thread(
            insert_project_log,
            request.app.state.database_path,
            level="WARNING",
            category="network",
            source=f"auth:{request.method} {request.url.path}",
            message=message,
            detail=(
                f"method={request.method}\n"
                f"path={request.url.path}\n"
                f"status_code={status_code}\n"
                f"client_ip={_client_ip(request) or '<empty>'}"
            ),
            trace_id=trace_id,
            error_code=str(status_code),
        )
    except Exception:
        _logger.exception(
            "Failed to persist auth failure log.",
            extra={"trace_id": trace_id, "category": "data"},
        )
    return JSONResponse(
        status_code=status_code,
        content={"ok": False, "message": message, "detail": message, "trace_id": trace_id},
    )


def _client_ip(request: Request, config: dict[str, Any] | None = None) -> str | None:
    """获取真实客户端 IP。

    默认使用 uvicorn 记录的直连 client.host。只有直连来源在可信代理网段内，
    才信任 X-Forwarded-For 首段，避免客户端伪造来源 IP 绕过白名单。
    """
    direct_host = request.client.host if request.client else None
    auth_cfg = config.get("auth") if isinstance(config, dict) else None
    trusted_proxies = auth_cfg.get("trusted_proxy_cidrs") if isinstance(auth_cfg, dict) else None
    if direct_host and _trusted_proxy_allowed(direct_host, trusted_proxies):
        forwarded = request.headers.get("x-forwarded-for") or request.headers.get("X-Forwarded-For") or ""
        forwarded = forwarded.strip()
        if forwarded:
            first = forwarded.split(",", 1)[0].strip()
            if first:
                return first
    return direct_host


def _ip_allowed(client_host: str | None, allowlist: Any) -> bool:
    """校验来源 IP 是否在白名单网段内。

    allowlist 为空 → 放行全部来源（向后兼容）。
    allowlist 非空 → 仅匹配的 CIDR 网段或单 IP 放行。
    """
    if not allowlist:
        return True
    if not client_host:
        return False
    # 兼容 IPv6 映射地址（::ffff:1.2.3.4）
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


def _trusted_proxy_allowed(client_host: str | None, allowlist: Any) -> bool:
    if not allowlist:
        return False
    return _ip_allowed(client_host, allowlist)


def _flag_enabled(value: Any) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, int):
        return value == 1
    if isinstance(value, str):
        return value.strip().lower() in {"1", "true", "yes", "on"}
    return False


def _external_ip_allowed(config: dict[str, Any], client_ip: str | None) -> bool:
    auth_cfg = config.get("auth") if isinstance(config, dict) else None
    if not isinstance(auth_cfg, dict):
        return True
    if not _flag_enabled(auth_cfg.get("external_ip_allowlist_enabled", False)):
        return True
    return _ip_allowed(client_ip, auth_cfg.get("external_ip_allowlist"))


def _auth_config(request: Request) -> dict[str, Any]:
    cached = getattr(request.app.state, "auth_config", None)
    if isinstance(cached, dict):
        return cached
    return get_yaml_config(request.app.state.project_root).as_dict()


def _sse_query_token(request: Request) -> str:
    if request.method.upper() == "GET" and request.url.path == "/api/ai/status/stream":
        return str(request.query_params.get("session_token") or "").strip()
    return ""


def _has_internal_auth_headers(request: Request) -> bool:
    return any(
        request.headers.get(name)
        for name in ("x-caller-id", "x-caller-timestamp", "x-caller-signature")
    )


def _internal_max_body_bytes(config: dict[str, Any]) -> int:
    auth_cfg = config.get("auth") if isinstance(config, dict) else None
    raw_value = None
    if isinstance(auth_cfg, dict):
        raw_value = auth_cfg.get("internal_max_body_bytes", auth_cfg.get("max_request_body_size"))
    try:
        value = int(raw_value)
    except (TypeError, ValueError):
        return _DEFAULT_INTERNAL_MAX_BODY_BYTES
    return value if value > 0 else _DEFAULT_INTERNAL_MAX_BODY_BYTES


async def _read_limited_body(request: Request, *, max_bytes: int) -> bytes:
    content_length = request.headers.get("content-length")
    if content_length:
        try:
            if int(content_length) > max_bytes:
                raise InternalAuthError("internal caller body is too large", status_code=413)
        except ValueError as exc:
            raise InternalAuthError("internal caller content length is invalid", status_code=400) from exc

    total = 0
    chunks: list[bytes] = []
    async for chunk in request.stream():
        total += len(chunk)
        if total > max_bytes:
            raise InternalAuthError("internal caller body is too large", status_code=413)
        chunks.append(chunk)
    body = b"".join(chunks)
    setattr(request, "_body", body)
    return body


async def _guest_route_allowed(request: Request, user: dict[str, Any]) -> bool:
    role = str(user.get("role") or "").strip().lower()
    if role != "guest":
        return True
    method = request.method.upper()
    path = request.url.path
    allowed = await asyncio.to_thread(
        role_allowed_for_route,
        request.app.state.database_path,
        role_key="guest",
        method=method,
        path=path,
    )
    permission_key = await asyncio.to_thread(
        route_permission_for_path,
        request.app.state.database_path,
        method=method,
        path=path,
    )
    await asyncio.to_thread(
        insert_permission_audit_log,
        request.app.state.database_path,
        trace_id=_trace_id(request),
        username=str(user.get("username") or ""),
        role_key="guest",
        permission_key=permission_key,
        method=method,
        path=path,
        decision="allow" if allowed else "deny",
        reason="" if allowed else "guest route is not allowed",
    )
    return allowed


def install_auth_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def _guard_api_session(request: Request, call_next):
        path = request.url.path

        if request.method == "OPTIONS" or not path.startswith("/api"):
            return await call_next(request)

        config = _auth_config(request)
        client_ip = _client_ip(request, config)
        if path in _PUBLIC_API_PATHS:
            if not _external_ip_allowed(config, client_ip):
                return await _auth_error(request, "来源 IP 不在外部访问白名单内", status_code=403)
            return await call_next(request)

        signature_target = path
        if request.url.query:
            signature_target = f"{signature_target}?{request.url.query}"
        body = b""
        try:
            has_internal_headers = _has_internal_auth_headers(request)
            if has_internal_headers:
                verify_internal_request_metadata(
                    config=config,
                    method=request.method,
                    path=signature_target,
                    headers=request.headers,
                    client_host=client_ip,
                )
            if has_internal_headers and request.method.upper() in _INTERNAL_BODY_SIGNED_METHODS:
                body = await _read_limited_body(
                    request,
                    max_bytes=_internal_max_body_bytes(config),
                )
            caller_id = verify_internal_request(
                config=config,
                method=request.method,
                path=signature_target,
                headers=request.headers,
                client_host=client_ip,
                body=body,
            )
        except InternalAuthError as exc:
            return await _auth_error(request, exc.message, status_code=exc.status_code)
        if caller_id is not None:
            request.state.auth_source = "internal"
            request.state.caller_id = caller_id
            request.state.auth_user = {
                "username": f"internal:{caller_id}",
                "display_name": f"internal:{caller_id}",
                "role": "internal",
                "user_type": "internal",
                "is_active": True,
                "last_login_at": "",
                "created_at": "",
                "updated_at": "",
            }
            request.state.auth_session = {
                "sub": f"internal:{caller_id}",
                "role": "internal",
                "sid": "",
                "exp": 0,
            }
            return await call_next(request)

        if not _external_ip_allowed(config, client_ip):
            return await _auth_error(request, "来源 IP 不在外部访问白名单内", status_code=403)

        token = extract_bearer_token(request.headers.get("Authorization"))
        if not token:
            token = _sse_query_token(request)
        if not token:
            return await _auth_error(request, "请先登录")

        # ── 双 Token (Redis) ──
        dual_mgr = get_dual_token_manager()
        if dual_mgr is None:
            return await _auth_error(request, "认证服务未就绪", status_code=503)

        try:
            token_user = await validate_access_token(token)
        except DualTokenError as exc:
            return await _auth_error(request, exc.msg, status_code=exc.status_code)
        except Exception:
            _logger.exception("Redis auth error", extra={"trace_id": _trace_id(request), "category": "network"})
            return await _auth_error(request, "认证服务暂时不可用", status_code=503)

        # 组装 user dict 以兼容现有 request.state 契约
        stored_user = None
        if token_user.role != "guest":
            stored_user = await asyncio.to_thread(
                get_console_user,
                request.app.state.database_path,
                token_user.username,
            )
            if stored_user is None:
                return await _auth_error(request, "账号不存在，请重新登录", status_code=401)
        user = {
            "username": token_user.username,
            "display_name": str((stored_user or {}).get("display_name") or token_user.username),
            "role": token_user.role,
            "user_type": str((stored_user or {}).get("user_type") or ("guest" if token_user.role == "guest" else "registered")),
            "is_active": bool((stored_user or {}).get("is_active", True)),
            "last_login_at": str((stored_user or {}).get("last_login_at") or ""),
            "created_at": str((stored_user or {}).get("created_at") or ""),
            "updated_at": str((stored_user or {}).get("updated_at") or ""),
        }
        if not user["is_active"]:
            return await _auth_error(request, "账号已停用，请联系管理员", status_code=403)
        if not await _guest_route_allowed(request, user):
            return await _auth_error(request, "游客账号无访问权限", status_code=403)
        request.state.auth_source = "external"
        request.state.caller_id = None
        request.state.auth_user = user
        request.state.auth_session = {
            "sub": token_user.username,
            "role": token_user.role,
            "sid": "",
            "exp": int(getattr(token_user, "expires_at", 0) or 0),
        }
        return await call_next(request)
