"""用户管理路由。"""

from __future__ import annotations

from api_common import ApiResponse, ValidationError, success_response
from fastapi import APIRouter, Depends, File, Query, UploadFile
from sqlalchemy.orm import Session

from app.api.deps import get_current_user, get_db_session, require_admin
from app.schemas.auth import UserInfo
from app.schemas.user import (
    AssignRolesRequest,
    AssignUserMenusRequest,
    AssignUserPermissionsRequest,
    CreateUserRequest,
    ResetPasswordRequest,
    UpdateProfileRequest,
)
from app.services.user_service import UserService

router = APIRouter()


@router.get("", response_model=ApiResponse, dependencies=[Depends(require_admin)])
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_db_session),
) -> dict:
    """分页查询用户列表（管理员）。"""
    service = UserService(session)
    return success_response(service.list_users(page=page, page_size=page_size))


@router.post("", response_model=ApiResponse, dependencies=[Depends(require_admin)])
def create_user(
    payload: CreateUserRequest,
    session: Session = Depends(get_db_session),
) -> dict:
    """管理员创建用户。"""
    service = UserService(session)
    result = service.create_user(
        username=payload.username,
        password=payload.password,
        nickname=payload.nickname,
        email=payload.email,
        phone=payload.phone,
        role_codes=payload.role_codes,
    )
    return success_response(result)


@router.put("/me", response_model=ApiResponse)
def update_profile(
    payload: UpdateProfileRequest,
    current_user: UserInfo = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> dict:
    """更新当前用户个人信息（含可选密码修改）。"""
    service = UserService(session)
    result = service.update_profile(
        user_id=current_user.id,
        nickname=payload.nickname,
        email=payload.email,
        phone=payload.phone,
        password=payload.password,
    )
    return success_response(result)


# 头像大小上限（3MB）
_AVATAR_MAX_SIZE = 3 * 1024 * 1024


@router.post("/avatar", response_model=ApiResponse)
def upload_avatar(
    file: UploadFile = File(...),
    current_user: UserInfo = Depends(get_current_user),
    session: Session = Depends(get_db_session),
) -> dict:
    """上传当前用户头像。

    限制：
    - 文件大小不超过 3MB
    - Content-Type 必须为 image/* 开头
    """
    content = file.file.read()
    if len(content) > _AVATAR_MAX_SIZE:
        raise ValidationError(message="头像文件不能超过 3MB")
    # 校验图片类型，防止上传非图片文件
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise ValidationError(message="仅支持上传图片文件")
    service = UserService(session)
    result = service.upload_avatar(
        user_id=current_user.id,
        filename=file.filename or "avatar",
        data=content,
        content_type=content_type,
    )
    return success_response(result)


@router.put(
    "/{user_id}/roles", response_model=ApiResponse, dependencies=[Depends(require_admin)]
)
def assign_roles(
    user_id: int,
    payload: AssignRolesRequest,
    session: Session = Depends(get_db_session),
) -> dict:
    """分配用户角色（管理员）。

    分配时会把角色权限/菜单复制到用户独立集合，之后用户可独立调整。
    """
    service = UserService(session)
    result = service.assign_roles(user_id=user_id, role_codes=payload.role_codes)
    return success_response(result)


@router.put(
    "/{user_id}/password",
    response_model=ApiResponse,
    dependencies=[Depends(require_admin)],
)
def reset_user_password(
    user_id: int,
    payload: ResetPasswordRequest,
    session: Session = Depends(get_db_session),
) -> dict:
    """重置指定用户密码（管理员，覆盖式，不校验旧密码）。"""
    service = UserService(session)
    result = service.reset_user_password(
        user_id=user_id, new_password=payload.new_password
    )
    return success_response(result)


@router.get(
    "/{user_id}/menus",
    response_model=ApiResponse,
    dependencies=[Depends(require_admin)],
)
def get_user_menus(
    user_id: int,
    session: Session = Depends(get_db_session),
) -> dict:
    """获取用户独立菜单列表（管理员）。"""
    service = UserService(session)
    return success_response(service.get_user_menus(user_id=user_id))


@router.put(
    "/{user_id}/menus",
    response_model=ApiResponse,
    dependencies=[Depends(require_admin)],
)
def assign_user_menus(
    user_id: int,
    payload: AssignUserMenusRequest,
    session: Session = Depends(get_db_session),
) -> dict:
    """分配用户独立菜单（覆盖式，管理员）。

    与角色菜单解耦：用户菜单为角色模板复制后的副本，可个性化增删。
    """
    service = UserService(session)
    result = service.assign_user_menus(user_id=user_id, menu_ids=payload.menu_ids)
    return success_response(result)


@router.get(
    "/{user_id}/permissions",
    response_model=ApiResponse,
    dependencies=[Depends(require_admin)],
)
def get_user_permissions(
    user_id: int,
    session: Session = Depends(get_db_session),
) -> dict:
    """获取用户独立权限列表（管理员）。"""
    service = UserService(session)
    return success_response(service.get_user_permissions(user_id=user_id))


@router.put(
    "/{user_id}/permissions",
    response_model=ApiResponse,
    dependencies=[Depends(require_admin)],
)
def assign_user_permissions(
    user_id: int,
    payload: AssignUserPermissionsRequest,
    session: Session = Depends(get_db_session),
) -> dict:
    """分配用户独立权限（覆盖式，管理员）。"""
    service = UserService(session)
    result = service.assign_user_permissions(
        user_id=user_id, permission_ids=payload.permission_ids
    )
    return success_response(result)
