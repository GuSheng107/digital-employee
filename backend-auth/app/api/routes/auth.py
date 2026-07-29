"""认证路由：注册、登录、刷新、登出、当前用户信息。

- POST /auth/register：用户注册，校验邀请码，返回双 token。
- POST /auth/login：用户名密码登录，返回双 token。
- POST /auth/refresh：用 refresh_token 换新的双 token。
- POST /auth/logout：登出，撤销当前 token。
- GET  /auth/me：返回当前登录用户信息（含角色与权限码）。

异常策略：业务异常统一使用 ``api_common.ApiException`` 子类，由全局
异常处理器转换为统一响应信封，路由层无需 try/except。
"""

from __future__ import annotations

from api_common import ApiResponse, TokenInvalidError, success_response
from fastapi import APIRouter, Depends, Request
from loguru import logger

from app.api.deps import _extract_bearer, get_auth_service, get_current_user
from app.schemas.auth import (
    LoginRequest,
    LogoutRequest,
    RefreshRequest,
    RegisterRequest,
    TokenPair,
    UserInfo,
)
from app.services.auth_service import AuthService

router = APIRouter()


@router.post("/register", response_model=ApiResponse)
def register(
    payload: RegisterRequest,
    service: AuthService = Depends(get_auth_service),
) -> dict:
    """用户注册，校验邀请码，签发双 token。"""
    token_pair: TokenPair = service.register(
        username=payload.username,
        password=payload.password,
        email=str(payload.email),
        phone=payload.phone,
        invite_code=payload.invite_code,
    )
    logger.info(
        "security_event=register username={} user_id={}",
        payload.username,
        token_pair.user_id,
    )
    return success_response(token_pair.model_dump())


@router.post("/login", response_model=ApiResponse)
def login(
    payload: LoginRequest,
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> dict:
    """用户名密码登录，签发双 token。"""
    client_ip = request.client.host if request.client else None
    token_pair: TokenPair = service.login(
        username=payload.username,
        password=payload.password,
        client_ip=client_ip,
    )
    logger.info(
        "security_event=login username={} user_id={} client_ip={}",
        payload.username,
        token_pair.user_id,
        client_ip,
    )
    return success_response(token_pair.model_dump())


@router.post("/refresh", response_model=ApiResponse)
def refresh(
    payload: RefreshRequest,
    service: AuthService = Depends(get_auth_service),
) -> dict:
    """用 refresh_token 换取新的双 token。"""
    token_pair: TokenPair = service.refresh(payload.refresh_token)
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
        raise TokenInvalidError(message="missing access_token")
    refresh_token = payload.refresh_token if payload else None
    service.logout(access_token=access_token, refresh_token=refresh_token)
    logger.info("security_event=logout")
    return success_response(message="logged out")


@router.get("/me", response_model=ApiResponse)
def me(
    current_user: UserInfo = Depends(get_current_user),
) -> dict:
    """返回当前登录用户信息（含角色 code 与权限 code 列表）。"""
    return success_response(current_user.model_dump())


@router.get("/authorization-context", response_model=ApiResponse)
def authorization_context(
    request: Request,
    service: AuthService = Depends(get_auth_service),
) -> dict:
    """返回跨服务鉴权所需的最小用户上下文。"""
    token = _extract_bearer(request.headers.get("Authorization"))
    return success_response(
        service.get_authorization_context(token).model_dump(exclude={"menus"})
    )
