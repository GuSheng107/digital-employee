"""认证路由：登录、刷新、登出、当前用户信息。

- POST /auth/login：用户名密码登录，返回双 token。
- POST /auth/refresh：用 refresh_token 换新的双 token。
- POST /auth/logout：登出，撤销当前 token。
- GET  /auth/me：返回当前登录用户信息（含角色与权限码）。
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, status

from app.api.deps import get_auth_service, get_current_user
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    TokenPair,
    UserInfo,
)
from app.schemas.common import ApiResponse
from app.services.auth_service import (
    AuthService,
    InvalidCredentialsError,
    InvalidTokenError,
    UserDisabledError,
)
from app.utils.response import success_response

router = APIRouter()


@router.post("/login", response_model=ApiResponse)
def login(
    payload: LoginRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> dict:
    """用户名密码登录，签发双 token。"""
    client_ip = request.client.host if request.client else None
    try:
        token_pair: TokenPair = service.login(
            username=payload.username,
            password=payload.password,
            client_ip=client_ip,
        )
    except (InvalidCredentialsError, UserDisabledError) as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    return success_response(token_pair.model_dump())


@router.post("/refresh", response_model=ApiResponse)
def refresh(
    payload: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
) -> dict:
    """用 refresh_token 换取新的双 token。"""
    try:
        token_pair: TokenPair = service.refresh(payload.refresh_token)
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=str(exc),
        ) from exc
    return success_response(token_pair.model_dump())


@router.post("/logout", response_model=ApiResponse)
def logout(
    request: Request,
    payload: LogoutRequest | None = None,
    service: AuthService = Depends(get_auth_service),
) -> dict:
    """登出，撤销 access_token 与可选的 refresh_token。

    优先从 Authorization 头取 access_token；请求体可携带 refresh_token
    一并撤销。
    """
    authorization = request.headers.get("Authorization", "")
    access_token = ""
    if authorization.lower().startswith("bearer "):
        access_token = authorization[7:].strip()
    if not access_token:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="missing access_token",
        )
    refresh_token = payload.refresh_token if payload else None
    service.logout(access_token=access_token, refresh_token=refresh_token)
    return success_response(message="logged out")


@router.get("/me", response_model=ApiResponse)
def me(
    current_user: UserInfo = Depends(get_current_user),
) -> dict:
    """返回当前登录用户信息（含角色 code 与权限 code 列表）。"""
    return success_response(current_user.model_dump())
