from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, Path as FastAPIPath, Request

from app.auth import create_session_id, get_guest_account_config, increment_guest_kick_counter, issue_session_token
from app.db.auth_store import (
    ADMIN_USERNAME,
    activate_console_user_session,
    authenticate_console_user,
    authenticate_guest_user,
    change_console_user_password,
    clear_console_user_session,
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
    if str(user.get("username") or "").strip() != ADMIN_USERNAME:
        raise AppError("需要管理员权限", status_code=403)
    return user


def require_non_guest(request: Request) -> dict[str, Any]:
    user = _current_user(request)
    if user.get("role") == "guest":
        raise AppError("游客账号无操作权限", status_code=403)
    return user


@router.post("/login", summary="登录控制台")
def login(
    payload: dict[str, Any] = Body(...),
    database_path: Path = Depends(get_database_path),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    username = str(payload.get("username") or "").strip()
    password = str(payload.get("password") or "")
    if not username or not password:
        raise ValidationError("请输入用户名和密码")
    user = authenticate_console_user(
        database_path,
        username=username,
        password=password,
    )
    if user is None:
        user = authenticate_guest_user(username=username, password=password)
    if user is None:
        raise AppError("用户名或密码错误", status_code=401)
    session_id = create_session_id()
    session = issue_session_token(
        project_root=project_root,
        user=user,
        session_id=session_id,
    )
    if user.get("role") != "guest":
        activate_console_user_session(
            database_path,
            username=user["username"],
            session_id=session_id,
            expires_at=int(session["expires_at"]),
        )
        refreshed_user = get_console_user(database_path, user["username"]) or user
    else:
        refreshed_user = user
    return {
        "user": refreshed_user,
        **session,
    }


@router.get("/session", summary="获取当前登录会话")
def current_session(request: Request) -> dict[str, Any]:
    user = _current_user(request)
    session = getattr(request.state, "auth_session", {})
    return {
        "user": user,
        "expires_at": int(session.get("exp") or 0),
    }


@router.post("/logout", summary="退出登录")
def logout(
    request: Request,
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    current_user = _current_user(request)
    session = getattr(request.state, "auth_session", {})
    if current_user.get("role") != "guest":
        clear_console_user_session(
            database_path,
            username=str(current_user.get("username") or ""),
            session_id=str(session.get("sid") or ""),
        )
    return {"ok": True}


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
def kick_user(
    request: Request,
    username: str = FastAPIPath(...),
    database_path: Path = Depends(get_database_path),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    require_admin(request)

    guest_cfg = get_guest_account_config()
    if guest_cfg is not None and username == guest_cfg["username"]:
        increment_guest_kick_counter(project_root)
        return {"ok": True, "message": "游客账号已全部强制下线"}
    clear_console_user_session(database_path, username=username)
    return {"ok": True, "message": f"用户 {username} 已强制下线"}
