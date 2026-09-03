"""权限码目录路由。"""

from __future__ import annotations

from api_common import ApiResponse, success_response
from auth_utils import PermissionCode
from fastapi import APIRouter, Depends

from app.api.deps import require_permission
from app.schemas.auth import UserInfo
from app.schemas.permission import CreatePermissionRequest
from app.services.permission_service import PermissionService

router = APIRouter()


@router.get(
    "",
    response_model=ApiResponse,
    dependencies=[
        Depends(
            require_permission(
                PermissionCode.PERMISSION_MANAGE,
                PermissionCode.PERMISSION_READONLY,
                PermissionCode.MENU_MANAGE,
                PermissionCode.MENU_READONLY,
            )
        )
    ],
)
def list_permissions() -> dict:
    """返回菜单与角色配置可引用的权限码目录。"""
    return success_response(PermissionService().list_permissions())


@router.post(
    "",
    response_model=ApiResponse,
)
def create_permission(
    payload: CreatePermissionRequest,
    _current_user: UserInfo = Depends(
        require_permission(PermissionCode.PERMISSION_MANAGE)
    ),
) -> dict:
    """动态创建权限码（仅用于菜单可见性与角色授权）。"""
    result = PermissionService().create_permission(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        module=payload.module,
    )
    return success_response(result)


@router.delete(
    "/{permission_id}",
    response_model=ApiResponse,
)
def delete_permission(
    permission_id: int,
    _current_user: UserInfo = Depends(
        require_permission(PermissionCode.PERMISSION_MANAGE)
    ),
) -> dict:
    """物理删除权限码（无角色/用户引用时）。"""
    result = PermissionService().delete_permission(permission_id=permission_id)
    return success_response(result)
