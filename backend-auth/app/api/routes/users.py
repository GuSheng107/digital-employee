"""用户管理路由。"""

from __future__ import annotations

from api_common import ApiResponse, ValidationError, success_response
from auth_utils import (
    AVATAR_MAX_SIZE_BYTES,
    BUSINESS_VIP_LEVELS,
    PermissionCode,
    get_vip_display,
)
from fastapi import APIRouter, Depends, File, Query, UploadFile

from app.api.deps import get_current_user, require_permission
from app.schemas.auth import UserInfo
from app.schemas.user import (
    AssignRolesRequest,
    AssignUserMenusRequest,
    AssignUserPermissionsRequest,
    CreateUserRequest,
    ResetPasswordRequest,
    UpdateProfileRequest,
    UpdateUserStatusRequest,
    UpdateVipRequest,
)
from app.services.user_service import UserService

router = APIRouter()


@router.get(
    "",
    response_model=ApiResponse,
    dependencies=[
        Depends(
            require_permission(
                PermissionCode.USER_MANAGE,
                PermissionCode.USER_PERMISSION,
            )
        )
    ],
)
def list_users(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    """分页查询用户列表（管理员）。"""
    service = UserService()
    return success_response(service.list_users(page=page, page_size=page_size))


@router.post(
    "",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.USER_MANAGE))],
)
def create_user(
    payload: CreateUserRequest,
) -> dict:
    """管理员创建用户。"""
    service = UserService()
    result = service.create_user(
        username=payload.username,
        password=payload.password,
        nickname=payload.nickname,
        email=str(payload.email) if payload.email else None,
        phone=payload.phone,
        role_codes=payload.role_codes,
        is_vip=payload.is_vip,
        vip_level=payload.vip_level,
        vip_expires_at=payload.vip_expires_at,
    )
    return success_response(result)


@router.put("/me", response_model=ApiResponse)
def update_profile(
    payload: UpdateProfileRequest,
    current_user: UserInfo = Depends(get_current_user),
) -> dict:
    """更新当前用户个人信息（含可选密码修改）。"""
    service = UserService()
    result = service.update_profile(
        user_id=current_user.id,
        nickname=payload.nickname,
        email=str(payload.email) if payload.email else None,
        phone=payload.phone,
        password=payload.password,
    )
    return success_response(result)


@router.get(
    "/vip-levels",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.USER_MANAGE))],
)
def list_vip_levels() -> dict:
    """返回可配置的业务 VIP 枚举。"""
    return success_response(
        [
            {
                "value": int(level),
                "label": get_vip_display(int(level)),
            }
            for level in BUSINESS_VIP_LEVELS
        ]
    )


@router.post("/avatar", response_model=ApiResponse)
def upload_avatar(
    file: UploadFile = File(...),
    current_user: UserInfo = Depends(get_current_user),
) -> dict:
    """上传当前用户头像。

    限制：
    - 文件大小不超过 3MB
    - Content-Type 必须为 image/* 开头
    """
    content = file.file.read()
    if len(content) > AVATAR_MAX_SIZE_BYTES:
        raise ValidationError(message="头像文件不能超过 3MB")
    # 校验图片类型，防止上传非图片文件
    content_type = file.content_type or ""
    if not content_type.startswith("image/"):
        raise ValidationError(message="仅支持上传图片文件")
    service = UserService()
    result = service.upload_avatar(
        user_id=current_user.id,
        filename=file.filename or "avatar",
        data=content,
        content_type=content_type,
    )
    return success_response(result)


@router.put(
    "/{user_id}/roles",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.USER_PERMISSION))],
)
def assign_roles(
    user_id: int,
    payload: AssignRolesRequest,
) -> dict:
    """分配用户角色（管理员）。

    分配时会把角色权限/菜单复制到用户独立集合，之后用户可独立调整。
    """
    service = UserService()
    result = service.assign_roles(user_id=user_id, role_codes=payload.role_codes)
    return success_response(result)


@router.put(
    "/{user_id}/password",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.USER_MANAGE))],
)
def reset_user_password(
    user_id: int,
    payload: ResetPasswordRequest,
) -> dict:
    """重置指定用户密码（管理员，覆盖式，不校验旧密码）。"""
    service = UserService()
    result = service.reset_user_password(user_id=user_id, new_password=payload.new_password)
    return success_response(result)


@router.put(
    "/{user_id}/vip",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.USER_MANAGE))],
)
def update_user_vip(
    user_id: int,
    payload: UpdateVipRequest,
) -> dict:
    """设置用户业务 VIP。"""
    return success_response(
        UserService().update_vip(
            user_id=user_id,
            is_vip=payload.is_vip,
            vip_level=payload.vip_level,
            vip_expires_at=payload.vip_expires_at,
        )
    )


@router.put(
    "/{user_id}/status",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.USER_MANAGE))],
)
def update_user_status(
    user_id: int,
    payload: UpdateUserStatusRequest,
) -> dict:
    """启用或停用用户。"""
    return success_response(
        UserService().update_status(
            user_id=user_id,
            status=payload.status,
        )
    )


@router.delete(
    "/{user_id}",
    response_model=ApiResponse,
)
def delete_user(
    user_id: int,
    current_user: UserInfo = Depends(
        require_permission(PermissionCode.USER_MANAGE)
    ),
) -> dict:
    """按当前管理员层级软删除用户并撤销其会话。"""
    return success_response(
        UserService().delete_user(
            user_id=user_id,
            actor_user_id=current_user.id,
            actor_role_codes=current_user.roles,
        )
    )


@router.get(
    "/{user_id}/menus",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.USER_PERMISSION))],
)
def get_user_menus(
    user_id: int,
) -> dict:
    """获取用户独立菜单列表（管理员）。"""
    service = UserService()
    return success_response(service.get_user_menus(user_id=user_id))


@router.put(
    "/{user_id}/menus",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.USER_PERMISSION))],
)
def assign_user_menus(
    user_id: int,
    payload: AssignUserMenusRequest,
) -> dict:
    """分配用户独立菜单（覆盖式，管理员）。

    与角色菜单解耦：用户菜单为角色模板复制后的副本，可个性化增删。
    """
    service = UserService()
    result = service.assign_user_menus(user_id=user_id, menu_ids=payload.menu_ids)
    return success_response(result)


@router.get(
    "/{user_id}/permissions",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.USER_PERMISSION))],
)
def get_user_permissions(
    user_id: int,
) -> dict:
    """获取用户独立权限列表（管理员）。"""
    service = UserService()
    return success_response(service.get_user_permissions(user_id=user_id))


@router.put(
    "/{user_id}/permissions",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.USER_PERMISSION))],
)
def assign_user_permissions(
    user_id: int,
    payload: AssignUserPermissionsRequest,
) -> dict:
    """分配用户独立权限（覆盖式，管理员）。"""
    service = UserService()
    result = service.assign_user_permissions(user_id=user_id, permission_ids=payload.permission_ids)
    return success_response(result)
