"""权限码目录路由。"""

from __future__ import annotations

from api_common import ApiResponse, success_response
from auth_utils import PermissionCode
from fastapi import APIRouter, Depends

from app.api.deps import require_permission
from app.services.permission_service import PermissionService

router = APIRouter()


@router.get(
    "",
    response_model=ApiResponse,
    dependencies=[
        Depends(
            require_permission(
                PermissionCode.USER_PERMISSION,
                PermissionCode.MENU_MANAGE,
            )
        )
    ],
)
def list_permissions() -> dict:
    """返回菜单与角色配置可引用的权限码目录。"""
    return success_response(PermissionService().list_permissions())
