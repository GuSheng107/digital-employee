from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, Path as FastAPIPath, Request

from app.auth import (
    DualTokenError,
    extract_bearer_token,
    get_dual_token_manager,
    get_guest_account_config,
    issue_token_pair,
    refresh_token_pair,
    revoke_token_pair,
    revoke_all_user_tokens,
    user_from_access_token,
)
from app.db.auth_store import (
    ADMIN_USERNAME,
    USER_TYPE_INTERNAL,
    USER_TYPE_REGISTERED,
    authenticate_console_user,
    authenticate_guest_user,
    change_console_user_password,
    create_console_user,
    delete_console_user,
    get_console_user,
    list_console_users,
    reset_console_user_password,
    update_console_user,
)
from app.exceptions import AppError, ValidationError
from app.routers._deps import get_database_path, get_project_root


router = APIRouter(prefix="/api/auth", tags=["auth"])


def _current_user(request: Request) -> dict[str, Any]:
    user = getattr(request.state, "auth_user", None)
    if not isinstance(user, dict):
        raise AppError("登录已过期，请重新登录", status_code=401)
    return user


def require_admin(request: Request) -> dict[str, Any]:
    user = _current_user(request)
    if getattr(request.state, "auth_source", "") == "internal" or user.get("role") == "internal":
        return user
    if str(user.get("username") or "").strip() != ADMIN_USERNAME:
        raise AppError("需要管理员权限", status_code=403)
    return user


def require_non_guest(request: Request) -> dict[str, Any]:
    user = _current_user(request)
    if getattr(request.state, "auth_source", "") == "internal" or user.get("role") == "internal":
        return user
    if user.get("role") == "guest":
        raise AppError("游客账号无操作权限", status_code=403)
    return user


def _normalize_user_type(value: Any) -> str:
    text = str(value or "").strip().lower()
    if text == USER_TYPE_INTERNAL:
        return USER_TYPE_INTERNAL
    return USER_TYPE_REGISTERED


@router.post("/login", summary="登录控制台（双 Token）")
async def login(
    payload: dict[str, Any] = Body(...),
    database_path: Path = Depends(get_database_path),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    if not username or not password:
        raise ValidationError("请输入用户名和密码")

    # 验证密码（控制台用户 / 游客账号）
    user = authenticate_console_user(database_path, username=username, password=password)
    if user is None:
        user = authenticate_guest_user(username=username, password=password)
    if user is None:
        raise AppError("用户名或密码错误", status_code=401)

    role = str(user.get("role") or "user")
    display_username = str(user.get("username") or "")
    user_type = str(user.get("user_type") or USER_TYPE_REGISTERED)

    # 双 Token 路径 (Redis 必需)
    dual_mgr = get_dual_token_manager()
    if dual_mgr is None:
        raise AppError("认证服务未就绪", status_code=503)

    pair = await issue_token_pair(display_username, role)
    return {
        "user": user,
        "access_token": pair.access_token,
        "refresh_token": pair.refresh_token,
        "expires_in": pair.expires_in,
        "token_type": "Bearer",
        "user_type": user_type,
    }


@router.get("/session", summary="获取当前登录会话")
async def current_session(request: Request) -> dict[str, Any]:
    user = _current_user(request)

    token = extract_bearer_token(request.headers.get("Authorization"))
    expires_at = 0
    if token:
        token_user = await user_from_access_token(token)
        if token_user:
            session_data = getattr(request.state, "auth_session", {})
            expires_at = int(session_data.get("exp") or 0)
    return {
        "user": user,
        "expires_at": expires_at,
    }


@router.post("/logout", summary="退出登录")
async def logout(
    request: Request,
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    """登出：从 Redis 撤销当前 access/refresh token pair。"""
    _current_user(request)

    token = extract_bearer_token(request.headers.get("Authorization"))
    if token:
        # revoke_token_pair 会同时撤销关联的 refresh token，幂等。
        await revoke_token_pair(token)
    return {"ok": True}


@router.post("/refresh", summary="刷新 Token (双 Token)")
async def refresh(
    payload: dict[str, Any] = Body(...),
) -> dict[str, Any]:
    """用 refresh_token 换取新的 token pair。旧 token 立即撤销，旧 access_token 保留 15min 缓冲。"""
    refresh_token_val = str(payload.get("refresh_token") or "").strip()
    if not refresh_token_val:
        raise AppError("refresh_token 不能为空", status_code=400)

    try:
        pair = await refresh_token_pair(refresh_token_val)
        return {
            "access_token": pair.access_token,
            "refresh_token": pair.refresh_token,
            "expires_in": pair.expires_in,
            "token_type": "Bearer",
        }
    except DualTokenError as exc:
        raise AppError(exc.msg, status_code=exc.status_code) from exc


@router.post("/password", summary="修改当前用户密码")
def change_password(
    request: Request,
    payload: dict[str, Any] = Body(...),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    current_user = _current_user(request)
    user = change_console_user_password(
        database_path,
        username=str(current_user.get("username") or ""),
        current_password=str(payload.get("current_password") or ""),
        new_password=str(payload.get("new_password") or ""),
    )
    return {"user": user}


@router.get("/users", summary="获取控制台用户列表")
def users(
    request: Request,
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_admin(request)
    return {"users": list_console_users(database_path)}


@router.post("/users", summary="添加控制台用户")
def add_user(
    request: Request,
    payload: dict[str, Any] = Body(...),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_admin(request)
    user = create_console_user(
        database_path,
        username=str(payload.get("username") or ""),
        password=str(payload.get("password") or ""),
        role=str(payload.get("role") or "user"),
        display_name=str(payload.get("display_name") or ""),
        user_type=_normalize_user_type(payload.get("user_type", payload.get("caller_type"))),
    )
    return {"user": user}


@router.put("/users/{username}", summary="编辑控制台用户")
def edit_user(
    request: Request,
    username: str = FastAPIPath(...),
    payload: dict[str, Any] = Body(...),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_admin(request)
    user = update_console_user(
        database_path,
        username=username,
        role=str(payload.get("role") or "user"),
        display_name=str(payload.get("display_name") or ""),
        user_type=payload.get("user_type", payload.get("caller_type")),
    )
    return {"user": user}


@router.post("/users/{username}/password", summary="重置控制台用户密码")
def reset_password(
    request: Request,
    username: str = FastAPIPath(...),
    payload: dict[str, Any] = Body(...),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_admin(request)
    user = reset_console_user_password(
        database_path,
        username=username,
        password=str(payload.get("password") or ""),
    )
    return {"user": user}


@router.delete("/users/{username}", summary="删除控制台用户")
def remove_user(
    request: Request,
    username: str = FastAPIPath(...),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    current_user = require_admin(request)
    if username == current_user.get("username"):
        raise AppError("不能删除当前登录用户", status_code=409)
    delete_console_user(database_path, username)
    return {"ok": True}


@router.get("/guest-account", summary="获取游客账号配置")
def guest_account(
    request: Request,
) -> dict[str, Any]:
    require_admin(request)

    cfg = get_guest_account_config()
    if cfg is None:
        return {"guest_account": None}
    return {
        "guest_account": {
            "username": cfg["username"],
            "password": cfg["password"],
        }
    }


@router.post("/users/{username}/kick", summary="强制下线用户")
async def kick_user(
    request: Request,
    username: str = FastAPIPath(...),
    database_path: Path = Depends(get_database_path),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    require_admin(request)

    # 双 Token — 撤销 Redis 中该用户所有 token
    dual_mgr = get_dual_token_manager()
    if dual_mgr is None:
        raise AppError("认证服务未就绪", status_code=503)
    count = await revoke_all_user_tokens(username)
    if count > 0:
        return {"ok": True, "message": f"用户 {username} 已强制下线（{count} 个 token 已撤销）"}
    return {"ok": True, "message": f"用户 {username} 无活跃 token"}
