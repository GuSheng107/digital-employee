"""菜单管理服务：列表（树形）、创建、更新、删除。

删除策略：软删除。若菜单有未删除的子菜单则阻止删除，避免孤儿节点。
菜单变更后调用方应触发前端缓存清理（前端通过 /auth/me 重新拉取）。
"""

from __future__ import annotations

from datetime import UTC, datetime

from api_common import PermissionDeniedError, ResourceNotFoundError, ValidationError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.menu import Menu


class MenuService:
    """菜单管理服务。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_menus(self) -> list[dict]:
        """列出所有未删除的菜单（扁平列表，按 parent_id、sort 升序）。

        前端可基于 parent_id 自行构建树形结构。
        """
        menus = self._session.scalars(
            select(Menu)
            .where(Menu.deleted_at.is_(None))
            .order_by(Menu.parent_id, Menu.sort, Menu.id)
        ).all()

        return [
            {
                "id": m.id,
                "parent_id": m.parent_id,
                "menu_type": m.menu_type,
                "title": m.title,
                "path": m.path,
                "component": m.component,
                "icon": m.icon,
                "permission": m.permission,
                "sort": m.sort,
                "visible": m.visible,
            }
            for m in menus
        ]

    def create_menu(
        self,
        *,
        parent_id: int,
        menu_type: int,
        title: str,
        path: str | None = None,
        component: str | None = None,
        icon: str | None = None,
        permission: str | None = None,
        sort: int = 0,
        visible: bool = True,
    ) -> dict:
        """创建菜单。

        Args:
            parent_id: 父菜单 ID，0 表示顶级。
            menu_type: 1=目录 2=菜单 3=按钮。
            title: 菜单标题。
            path: 前端路由路径（菜单类型必填）。
            component: 前端组件路径。
            icon: 图标名（antd 图标组件名，如 DatabaseOutlined）。
            permission: 所需权限码。
            sort: 排序值，升序。
            visible: 是否可见。

        Raises:
            ValidationError: parent_id 指向不存在或已删除的菜单。
        """
        if parent_id != 0:
            parent = self._session.get(Menu, parent_id)
            if parent is None or parent.deleted_at is not None:
                raise ValidationError(message=f"父菜单不存在：{parent_id}")

        menu = Menu(
            parent_id=parent_id,
            menu_type=menu_type,
            title=title,
            path=path,
            component=component,
            icon=icon,
            permission=permission,
            sort=sort,
            visible=visible,
        )
        self._session.add(menu)
        self._session.flush()

        result = self._to_dict(menu)
        self._session.commit()
        return result

    def update_menu(
        self,
        *,
        menu_id: int,
        parent_id: int | None = None,
        menu_type: int | None = None,
        title: str | None = None,
        path: str | None = None,
        component: str | None = None,
        icon: str | None = None,
        permission: str | None = None,
        sort: int | None = None,
        visible: bool | None = None,
    ) -> dict:
        """更新菜单（字段未传则不修改）。

        Raises:
            ResourceNotFoundError: 菜单不存在。
            ValidationError: parent_id 指向不存在菜单，或形成自引用/环。
        """
        menu = self._session.get(Menu, menu_id)
        if menu is None or menu.deleted_at is not None:
            raise ResourceNotFoundError(message="菜单不存在")

        if parent_id is not None and parent_id != menu.parent_id:
            # 不允许把菜单挂到自己下面
            if parent_id == menu_id:
                raise ValidationError(message="不能将菜单挂载到自身下")
            # 不允许把菜单挂到自己的子孙下（避免环）
            if parent_id != 0 and self._is_descendant(parent_id, menu_id):
                raise ValidationError(message="不能将菜单挂载到其子菜单下")
            if parent_id != 0:
                parent = self._session.get(Menu, parent_id)
                if parent is None or parent.deleted_at is not None:
                    raise ValidationError(message=f"父菜单不存在：{parent_id}")
            menu.parent_id = parent_id

        if menu_type is not None:
            menu.menu_type = menu_type
        if title is not None:
            menu.title = title
        if path is not None:
            menu.path = path
        if component is not None:
            menu.component = component
        if icon is not None:
            menu.icon = icon
        if permission is not None:
            menu.permission = permission
        if sort is not None:
            menu.sort = sort
        if visible is not None:
            menu.visible = visible

        result = self._to_dict(menu)
        self._session.commit()
        return result

    def delete_menu(self, *, menu_id: int) -> dict:
        """删除菜单（软删除）。

        若仍有未删除的子菜单，则阻止删除，避免孤儿节点。

        Raises:
            ResourceNotFoundError: 菜单不存在。
            PermissionDeniedError: 仍存在子菜单。
        """
        menu = self._session.get(Menu, menu_id)
        if menu is None or menu.deleted_at is not None:
            raise ResourceNotFoundError(message="菜单不存在")

        # 检查是否有未删除的子菜单
        child_count = self._session.scalar(
            select(Menu.id)
            .where(
                Menu.parent_id == menu_id,
                Menu.deleted_at.is_(None),
            )
            .limit(1)
        )
        if child_count is not None:
            raise PermissionDeniedError(message="该菜单下仍有子菜单，请先删除子菜单")

        menu.deleted_at = datetime.now(UTC)
        self._session.commit()
        return {"menu_id": menu_id, "deleted": True}

    # ---------- 内部工具方法 ----------

    def _is_descendant(self, candidate_id: int, ancestor_id: int) -> bool:
        """判断 candidate_id 是否为 ancestor_id 的子孙（避免环）。

        从 candidate 向上回溯 parent_id 链，若遇到 ancestor_id 则为子孙。
        """
        current_id = candidate_id
        visited: set[int] = set()
        while current_id != 0 and current_id not in visited:
            visited.add(current_id)
            menu = self._session.get(Menu, current_id)
            if menu is None or menu.deleted_at is not None:
                return False
            if menu.parent_id == ancestor_id:
                return True
            current_id = menu.parent_id
        return False

    def _to_dict(self, menu: Menu) -> dict:
        return {
            "id": menu.id,
            "parent_id": menu.parent_id,
            "menu_type": menu.menu_type,
            "title": menu.title,
            "path": menu.path,
            "component": menu.component,
            "icon": menu.icon,
            "permission": menu.permission,
            "sort": menu.sort,
            "visible": menu.visible,
        }
