"""菜单管理路由（仅管理员可调用）。

- GET    /menus         列出所有菜单（扁平列表）
- POST   /menus         创建菜单
- PUT    /menus/{id}    更新菜单
- DELETE /menus/{id}    删除菜单（软删除）

菜单变更后前端需重新拉取 /auth/me 刷新本地缓存。
"""

from __future__ import annotations

from api_common import ApiResponse, success_response
from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.api.deps import get_db_session, require_admin
from app.schemas.menu import CreateMenuRequest, UpdateMenuRequest
from app.services.menu_service import MenuService

router = APIRouter()


@router.get(
    "",
    response_model=ApiResponse,
    dependencies=[Depends(require_admin)],
)
def list_menus(session: Session = Depends(get_db_session)) -> dict:
    """列出所有菜单（扁平列表，按 parent_id、sort 升序）。"""
    service = MenuService(session)
    return success_response(service.list_menus())


@router.post(
    "",
    response_model=ApiResponse,
    dependencies=[Depends(require_admin)],
)
def create_menu(
    payload: CreateMenuRequest,
    session: Session = Depends(get_db_session),
) -> dict:
    """创建菜单。"""
    service = MenuService(session)
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


@router.put(
    "/{menu_id}",
    response_model=ApiResponse,
    dependencies=[Depends(require_admin)],
)
def update_menu(
    menu_id: int,
    payload: UpdateMenuRequest,
    session: Session = Depends(get_db_session),
) -> dict:
    """更新菜单（字段未传则不修改）。"""
    service = MenuService(session)
    result = service.update_menu(
        menu_id=menu_id,
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


@router.delete(
    "/{menu_id}",
    response_model=ApiResponse,
    dependencies=[Depends(require_admin)],
)
def delete_menu(
    menu_id: int,
    session: Session = Depends(get_db_session),
) -> dict:
    """删除菜单（软删除）。若仍有子菜单则拒绝。"""
    service = MenuService(session)
    result = service.delete_menu(menu_id=menu_id)
    return success_response(result)
