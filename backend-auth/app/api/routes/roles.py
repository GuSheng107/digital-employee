"""角色管理路由（需要 role:manage 权限）。"""

from __future__ import annotations

from api_common import ApiResponse, success_response
from auth_utils import PermissionCode
from fastapi import APIRouter, Depends

from app.api.deps import require_permission
from app.schemas.role import AssignMenusRequest, CreateRoleRequest, UpdateRoleRequest
from app.services.role_service import RoleService

router = APIRouter()


@router.get(
    "",
    response_model=ApiResponse,
    dependencies=[
        Depends(
            require_permission(
                PermissionCode.USER_PERMISSION,
                PermissionCode.USER_MANAGE,
            )
        )
    ],
)
def list_roles() -> dict:
    """列出所有角色。"""
    service = RoleService()
    return success_response(service.list_roles())


@router.post(
    "",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.USER_PERMISSION))],
)
def create_role(
    payload: CreateRoleRequest,
) -> dict:
    """创建自定义角色。"""
    service = RoleService()
    result = service.create_role(
        code=payload.code,
        name=payload.name,
        description=payload.description,
        menu_ids=payload.menu_ids,
    )
    return success_response(result)


@router.put(
    "/{role_id}",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.USER_PERMISSION))],
)
def update_role(
    role_id: int,
    payload: UpdateRoleRequest,
) -> dict:
    """更新角色信息（名称/描述/菜单）。"""
    service = RoleService()
    result = service.update_role(
        role_id=role_id,
        name=payload.name,
        description=payload.description,
        menu_ids=payload.menu_ids,
    )
    return success_response(result)


@router.delete(
    "/{role_id}",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.USER_PERMISSION))],
)
def delete_role(
    role_id: int,
) -> dict:
    """删除角色（软删除，内置角色不可删）。"""
    service = RoleService()
    result = service.delete_role(role_id=role_id)
    return success_response(result)


@router.get(
    "/{role_id}/menus",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.USER_PERMISSION))],
)
def get_role_menus(
    role_id: int,
) -> dict:
    """获取角色关联的菜单列表。"""
    service = RoleService()
    return success_response(service.get_role_menus(role_id=role_id))


@router.put(
    "/{role_id}/menus",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.USER_PERMISSION))],
)
def assign_menus(
    role_id: int,
    payload: AssignMenusRequest,
) -> dict:
    """分配角色菜单（覆盖式）。"""
    service = RoleService()
    result = service.assign_menus(role_id=role_id, menu_ids=payload.menu_ids)
    return success_response(result)
