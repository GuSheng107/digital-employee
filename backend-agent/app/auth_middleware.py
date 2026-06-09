from __future__ import annotations

"""API 认证中间件模块。

实现基于 Bearer Token 和 Session Token 的 API 请求认证，
验证会话令牌的有效性并检查用户账号状态，保护需要认证的 API 端点。
"""

import time
from typing import Any

from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

from app.auth import AuthTokenError, extract_bearer_token, verify_session_token
from app.db.auth_store import get_console_user_for_session
from app.exceptions import AppError


_PUBLIC_API_PATHS = frozenset({
    "/api/auth/login",
})


def _auth_error(message: str, *, status_code: int = 401) -> JSONResponse:
    return JSONResponse(
        status_code=status_code,
        content={
            "ok": False,
            "message": message,
            "detail": message,
        },
    )


def install_auth_middleware(app: FastAPI) -> None:
    @app.middleware("http")
    async def _guard_api_session(request: Request, call_next):
        path = request.url.path
        if request.method == "OPTIONS" or not path.startswith("/api") or path in _PUBLIC_API_PATHS:
            return await call_next(request)

        token = extract_bearer_token(request.headers.get("Authorization"))
        if not token:
            token = str(request.query_params.get("session_token") or "").strip()
        if not token:
            return _auth_error("登录已过期，请重新登录")

        try:
            payload = verify_session_token(
                project_root=request.app.state.project_root,
                token=token,
            )
            role = str(payload.get("role") or "user")
            if role == "guest":
                user = {
                    "username": str(payload.get("sub") or ""),
                    "display_name": "游客",
                    "role": "guest",
                    "is_active": True,
                    "last_login_at": "",
                    "created_at": "",
                    "updated_at": "",
                }
            else:
                user = get_console_user_for_session(
                    request.app.state.database_path,
                    username=str(payload.get("sub") or ""),
                    session_id=str(payload.get("sid") or ""),
                    now_seconds=int(time.time()),
                )
        except AuthTokenError as exc:
            return _auth_error(str(exc) or "登录已过期，请重新登录")
        except AppError as exc:
            return _auth_error(exc.message, status_code=exc.status_code)

        if not user or not user.get("is_active"):
            return _auth_error("账号已在其他地方登录，请重新登录")

        request.state.auth_user = user
        request.state.auth_session = {
            **payload,
            "role": user.get("role", "user"),
        }
        return await call_next(request)
