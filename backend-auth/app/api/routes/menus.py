"""菜单管理路由（仅管理员可调用）。

- GET    /menus         列出所有菜单（扁平列表）
- POST   /menus         创建菜单
- PUT    /menus/{id}    更新菜单
- DELETE /menus/{id}    删除菜单（软删除）

菜单变更后前端需重新拉取 /auth/me 刷新本地缓存。
"""

from __future__ import annotations

from api_common import ApiResponse, success_response
from auth_utils import PermissionCode
from fastapi import APIRouter, Depends

from app.api.deps import require_permission
from app.schemas.menu import CreateMenuRequest, UpdateMenuRequest
from app.services.menu_service import MenuService

router = APIRouter()


@router.get(
    "",
    response_model=ApiResponse,
    dependencies=[
        Depends(
            require_permission(
                PermissionCode.MENU_MANAGE,
                PermissionCode.USER_PERMISSION,
            )
        )
    ],
)
def list_menus() -> dict:
    """列出所有菜单（扁平列表，按 parent_id、sort 升序）。"""
    service = MenuService()
    return success_response(service.list_menus())


@router.post(
    "",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.MENU_MANAGE))],
)
def create_menu(
    payload: CreateMenuRequest,
) -> dict:
    """创建菜单。"""
    service = MenuService()
    result = service.create_menu(
        parent_id=payload.parent_id,
        menu_type=payload.menu_type,
        title=payload.title,
        path=payload.path,
        component=payload.component,
        icon=payload.icon,
        permission=payload.permission,
        sort=payload.sort,
        visible=payload.visible,
    )
    return success_response(result)


@router.post(
    "/{menu_id}",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.MENU_MANAGE))],
)
def update_menu(
    menu_id: int,
    payload: UpdateMenuRequest,
) -> dict:
    """更新菜单（字段未传则不修改）。"""
    service = MenuService()
    result = service.update_menu(
        menu_id=menu_id,
        **payload.model_dump(exclude_unset=True),
    )
    return success_response(result)


@router.delete(
    "/{menu_id}",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.MENU_MANAGE))],
)
def delete_menu(
    menu_id: int,
) -> dict:
    """删除菜单（软删除）。若仍有子菜单则拒绝。"""
    service = MenuService()
    result = service.delete_menu(menu_id=menu_id)
    return success_response(result)
