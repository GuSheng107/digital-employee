"""角色管理服务：列表、创建、更新、删除、菜单分配。"""

from __future__ import annotations

from datetime import UTC, datetime

from api_common import DuplicateResourceError, PermissionDeniedError, ResourceNotFoundError
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.menu import Menu
from app.models.role import Role


class RoleService:
    """角色管理服务。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def list_roles(self) -> list[dict]:
        """列出所有角色（含关联的菜单 ID 列表）。"""
        roles = self._session.scalars(
            select(Role).where(Role.deleted_at.is_(None)).order_by(Role.id)
        ).all()

        items = []
        for role in roles:
            menu_ids = [m.id for m in role.menus if m.deleted_at is None]
            items.append(
                {
                    "id": role.id,
                    "code": role.code,
                    "name": role.name,
                    "description": role.description,
                    "is_builtin": role.is_builtin,
                    "menu_ids": menu_ids,
                }
            )
        return items

    def create_role(
        self,
        *,
        code: str,
        name: str,
        description: str = "",
        menu_ids: list[int] | None = None,
    ) -> dict:
        """创建自定义角色。

        Args:
            code: 角色代码，需唯一。
            name: 角色名称。
            description: 角色描述。
            menu_ids: 关联菜单 ID 列表。

        Raises:
            DuplicateResourceError: 角色代码已存在。
        """
        existing = self._session.scalars(
            select(Role).where(Role.code == code, Role.deleted_at.is_(None))
        ).first()
        if existing is not None:
            raise DuplicateResourceError(message="角色代码已存在")

        role = Role(
            code=code,
            name=name,
            description=description,
            is_builtin=False,
        )
        self._session.add(role)
        self._session.flush()

        if menu_ids:
            menus = list(
                self._session.scalars(
                    select(Menu).where(Menu.id.in_(menu_ids), Menu.deleted_at.is_(None))
                ).all()
            )
            role.menus = menus

        self._session.commit()

        return {
            "id": role.id,
            "code": role.code,
            "name": role.name,
            "description": role.description,
            "is_builtin": role.is_builtin,
            "menu_ids": [m.id for m in role.menus if m.deleted_at is None],
        }

    def update_role(
        self,
        *,
        role_id: int,
        name: str | None = None,
        description: str | None = None,
        menu_ids: list[int] | None = None,
    ) -> dict:
        """更新角色信息。

        内置角色（is_builtin=True）不允许修改名称，仅允许修改描述与菜单。

        Raises:
            ResourceNotFoundError: 角色不存在。
            PermissionDeniedError: 尝试修改内置角色名称。
        """
        role = self._session.get(Role, role_id)
        if role is None or role.deleted_at is not None:
            raise ResourceNotFoundError(message="角色不存在")

        if name is not None:
            if role.is_builtin:
                raise PermissionDeniedError(message="内置角色不允许修改名称")
            role.name = name
        if description is not None:
            role.description = description
        if menu_ids is not None:
            menus = list(
                self._session.scalars(
                    select(Menu).where(Menu.id.in_(menu_ids), Menu.deleted_at.is_(None))
                ).all()
            ) if menu_ids else []
            role.menus = menus

        self._session.commit()

        return {
            "id": role.id,
            "code": role.code,
            "name": role.name,
            "description": role.description,
            "is_builtin": role.is_builtin,
            "menu_ids": [m.id for m in role.menus if m.deleted_at is None],
        }

    def delete_role(self, *, role_id: int) -> dict:
        """删除角色（软删除）。

        内置角色不可删除。如果角色仍关联用户，则阻止删除。

        Raises:
            ResourceNotFoundError: 角色不存在。
            PermissionDeniedError: 内置角色不可删除或角色仍关联用户。
        """
        role = self._session.get(Role, role_id)
        if role is None or role.deleted_at is not None:
            raise ResourceNotFoundError(message="角色不存在")

        if role.is_builtin:
            raise PermissionDeniedError(message="内置角色不可删除")

        # 检查是否仍有关联用户
        if role.users:
            user_count = len([u for u in role.users if u.deleted_at is None])
            if user_count > 0:
                raise PermissionDeniedError(
                    message=f"角色仍关联 {user_count} 个用户，请先解除关联后再删除"
                )

        # 软删除：清除关联菜单后标记删除
        role.menus = []
        role.deleted_at = datetime.now(UTC)
        self._session.commit()

        return {"role_id": role_id, "deleted": True}

    def get_role_menus(self, *, role_id: int) -> list[dict]:
        """获取角色关联的菜单列表。"""
        role = self._session.get(Role, role_id)
        if role is None or role.deleted_at is not None:
            raise ResourceNotFoundError(message="角色不存在")

        menus = [m for m in role.menus if m.deleted_at is None]
        return [
            {
                "id": m.id,
                "parent_id": m.parent_id,
                "menu_type": m.menu_type,
                "title": m.title,
                "path": m.path,
                "icon": m.icon,
                "permission": m.permission,
                "sort": m.sort,
                "visible": m.visible,
            }
            for m in menus
        ]

    def assign_menus(self, *, role_id: int, menu_ids: list[int]) -> dict:
        """分配角色菜单（覆盖式）。"""
        role = self._session.get(Role, role_id)
        if role is None or role.deleted_at is not None:
            raise ResourceNotFoundError(message="角色不存在")

        # 查询目标菜单
        menus: list[Menu] = []
        if menu_ids:
            menus = list(
                self._session.scalars(
                    select(Menu).where(Menu.id.in_(menu_ids), Menu.deleted_at.is_(None))
                ).all()
            )

        # 覆盖式更新
        role.menus = menus
        self._session.commit()

        return {
            "role_id": role_id,
            "menu_ids": [m.id for m in role.menus],
        }
