"""FastAPI 通用依赖。

- ``verify_api_key``：保护非健康检查类业务端点（与 backend-data 一致）。
- ``get_auth_service``：构造带数据库会话的 AuthService。
- ``get_current_user``：从 Authorization 头解析 access_token，返回当前用户。
"""

from __future__ import annotations

import secrets
from collections.abc import Generator

from fastapi import Depends, Header, HTTPException, status
from sqlalchemy.orm import Session

from app.core.config import settings
from app.core.database import get_db_session
from app.schemas.auth import UserInfo
from app.services.auth_service import AuthError, AuthService, InvalidTokenError


def verify_api_key(x_api_key: str | None = Header(default=None)) -> None:
    """校验请求头 ``X-API-Key`` 是否与服务端配置一致。

    当 ``API_KEY`` 未配置时跳过校验，便于本地开发；
    生产环境应通过环境变量显式配置 ``API_KEY``。

    使用 ``secrets.compare_digest`` 进行常量时间比较，避免时序攻击。

    Args:
        x_api_key: 请求头 ``X-API-Key`` 的值，缺失或为空表示未携带。

    Raises:
        HTTPException: 当 ``API_KEY`` 已配置但请求头缺失或不匹配时，
            返回 401 未授权。
    """
    expected = settings.api_key
    if not expected:
        return
    if not x_api_key or not secrets.compare_digest(x_api_key, expected):
        raise HTTPException(status_code=401, detail="invalid api key")


def get_auth_service(
    session: Session = Depends(get_db_session),
) -> Generator[AuthService, None, None]:
    """构造 AuthService 并在请求结束后关闭会话。"""
    service = AuthService(session)
    try:
        yield service
    finally:
        session.close()


def _extract_bearer(authorization: str | None) -> str:
    """从 Authorization 头解析 Bearer token。"""
    if not authorization:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing authorization header",
        )
    parts = authorization.split(" ", 1)
    if len(parts) != 2 or parts[0].lower() != "bearer":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="invalid authorization scheme",
        )
    token = parts[1].strip()
    if not token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="empty bearer token",
        )
    return token


def get_current_user(
    authorization: str | None = Header(default=None),
    service: AuthService = Depends(get_auth_service),
) -> UserInfo:
    """解析 access_token 并返回当前登录用户信息。

    Raises:
        HTTPException: 401 当 token 无效/过期或用户被禁用。
    """
    token = _extract_bearer(authorization)
    try:
        return service.get_current_user(token)
    except (InvalidTokenError, AuthError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
