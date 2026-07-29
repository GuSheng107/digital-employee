"""菜单管理服务：列表（树形）、创建、更新、删除。

删除策略：软删除。若菜单有未删除的子菜单则阻止删除，避免孤儿节点。
菜单变更后调用方应触发前端缓存清理（前端通过 /auth/me 重新拉取）。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, cast

from api_common import (
    ConflictError,
    DuplicateResourceError,
    ResourceNotFoundError,
    ValidationError,
)
from auth_utils import MenuType
from sqlalchemy import literal, select
from sqlalchemy.orm import Session

from app.models.menu import Menu
from app.models.permission import Permission


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
        self._validate_parent(parent_id)
        self._validate_permission_code(permission)
        self._ensure_unique_menu(
            parent_id=parent_id,
            title=title,
            path=path,
        )

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
        updates: dict[str, Any],
    ) -> dict:
        """更新菜单，并区分字段未传与显式 ``null`` 清空。

        Raises:
            ResourceNotFoundError: 菜单不存在。
            ValidationError: parent_id 指向不存在菜单，或形成自引用/环。
        """
        menu = self._session.get(Menu, menu_id)
        if menu is None or menu.deleted_at is not None:
            raise ResourceNotFoundError(message="菜单不存在")

        if "parent_id" in updates:
            parent_id = cast(int, updates["parent_id"])
        else:
            parent_id = menu.parent_id
        if parent_id != menu.parent_id:
            # 不允许把菜单挂到自己下面
            if parent_id == menu_id:
                raise ValidationError(message="不能将菜单挂载到自身下")
            # 不允许把菜单挂到自己的子孙下（避免环）
            if parent_id != 0 and self._is_descendant(parent_id, menu_id):
                raise ValidationError(message="不能将菜单挂载到其子菜单下")
            self._validate_parent(parent_id)
            menu.parent_id = parent_id

        if "menu_type" in updates:
            menu_type = cast(int, updates["menu_type"])
            if menu_type != MenuType.DIRECTORY and self._has_children(menu_id):
                raise ValidationError(message="存在子菜单的目录不能改为菜单或按钮")
            menu.menu_type = menu_type
        if "title" in updates:
            menu.title = cast(str, updates["title"])
        if "path" in updates:
            menu.path = self._normalize_optional_text(cast(str | None, updates["path"]))
        if "component" in updates:
            menu.component = self._normalize_optional_text(
                cast(str | None, updates["component"])
            )
        if "icon" in updates:
            menu.icon = self._normalize_optional_text(cast(str | None, updates["icon"]))
        if "permission" in updates:
            normalized_permission = self._normalize_optional_text(
                cast(str | None, updates["permission"])
            )
            self._validate_permission_code(normalized_permission)
            menu.permission = normalized_permission
        if "sort" in updates:
            menu.sort = cast(int, updates["sort"])
        if "visible" in updates:
            menu.visible = cast(bool, updates["visible"])

        self._ensure_unique_menu(
            parent_id=menu.parent_id,
            title=menu.title,
            path=menu.path,
            exclude_menu_id=menu.id,
        )

        result = self._to_dict(menu)
        self._session.commit()
        return result

    def delete_menu(self, *, menu_id: int) -> dict:
        """删除菜单（软删除）。

        若仍有未删除的子菜单，则阻止删除，避免孤儿节点。

        Raises:
            ResourceNotFoundError: 菜单不存在。
            ConflictError: 仍存在子菜单。
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
            raise ConflictError(message="该菜单下仍有子菜单，请先删除子菜单")

        menu.deleted_at = datetime.now(UTC)
        self._session.commit()
        return {"menu_id": menu_id, "deleted": True}

    # ---------- 内部工具方法 ----------

    def _validate_parent(self, parent_id: int) -> None:
        """校验父节点存在且必须是目录。"""
        if parent_id == 0:
            return
        parent = self._session.get(Menu, parent_id)
        if parent is None or parent.deleted_at is not None:
            raise ValidationError(message=f"父菜单不存在：{parent_id}")
        if parent.menu_type != MenuType.DIRECTORY:
            raise ValidationError(message="只有目录节点可以包含子菜单")

    def _validate_permission_code(self, permission_code: str | None) -> None:
        """拒绝菜单引用权限表中不存在的权限码。"""
        if not permission_code:
            return
        permission_id = self._session.scalar(
            select(Permission.id).where(Permission.code == permission_code).limit(1)
        )
        if permission_id is None:
            raise ValidationError(message=f"权限码不存在：{permission_code}")

    def _has_children(self, menu_id: int) -> bool:
        """判断菜单是否存在未删除子节点。"""
        child_id = self._session.scalar(
            select(Menu.id)
            .where(
                Menu.parent_id == menu_id,
                Menu.deleted_at.is_(None),
            )
            .limit(1)
        )
        return child_id is not None

    def _ensure_unique_menu(
        self,
        *,
        parent_id: int,
        title: str,
        path: str | None,
        exclude_menu_id: int | None = None,
    ) -> None:
        """校验同级标题与非空路由路径唯一，防止真实重复菜单数据。"""
        title_statement = select(Menu.id).where(
            Menu.parent_id == parent_id,
            Menu.title == title,
            Menu.deleted_at.is_(None),
        )
        if exclude_menu_id is not None:
            title_statement = title_statement.where(Menu.id != exclude_menu_id)
        if self._session.scalar(title_statement.limit(1)) is not None:
            raise DuplicateResourceError(message="同一父菜单下标题不能重复")

        if not path:
            return
        path_statement = select(Menu.id).where(
            Menu.path == path,
            Menu.deleted_at.is_(None),
        )
        if exclude_menu_id is not None:
            path_statement = path_statement.where(Menu.id != exclude_menu_id)
        if self._session.scalar(path_statement.limit(1)) is not None:
            raise DuplicateResourceError(message="菜单路由路径不能重复")

    def _is_descendant(self, candidate_id: int, ancestor_id: int) -> bool:
        """使用递归 CTE 判断候选节点是否位于祖先节点的子树中。"""
        descendants = (
            select(Menu.id)
            .where(
                Menu.id == candidate_id,
                Menu.deleted_at.is_(None),
            )
            .cte(name="menu_ancestors", recursive=True)
        )
        descendants = descendants.union_all(
            select(Menu.parent_id).join(
                descendants,
                Menu.id == descendants.c.id,
            )
        )
        return self._session.scalar(
            select(literal(True))
            .where(descendants.c.id == ancestor_id)
            .limit(1)
        ) is True

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

    @staticmethod
    def _normalize_optional_text(value: str | None) -> str | None:
        """把显式空字符串归一化为 NULL。"""
        if value is None:
            return None
        normalized = value.strip()
        return normalized or None
