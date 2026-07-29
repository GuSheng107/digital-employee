"""角色管理编排，实际数据操作由 backend-data 完成。"""

from __future__ import annotations

from typing import Any

from data_client import DataClient, get_data_client


class RoleService:
    """角色管理代理。"""

    def __init__(self, data_client: DataClient | None = None) -> None:
        self._data = data_client or get_data_client()

    def list_roles(self) -> list[dict[str, Any]]:
        """列出可管理角色。"""
        return self._data.list_roles()

    def create_role(
        self,
        *,
        code: str,
        name: str,
        actor_role_codes: list[str],
        actor_permission_codes: list[str],
        description: str = "",
        menu_ids: list[int] | None = None,
    ) -> dict:
        """创建角色。"""
        return self._data.create_role(
            code=code,
            name=name,
            description=description,
            menu_ids=menu_ids or [],
            actor_role_codes=actor_role_codes,
            actor_permission_codes=actor_permission_codes,
        )

    def update_role(
        self,
        *,
        role_id: int,
        actor_role_codes: list[str],
        actor_permission_codes: list[str],
        name: str | None = None,
        description: str | None = None,
        menu_ids: list[int] | None = None,
    ) -> dict:
        """更新角色。"""
        return self._data.update_role(
            role_id=role_id,
            name=name,
            description=description,
            menu_ids=menu_ids,
            actor_role_codes=actor_role_codes,
            actor_permission_codes=actor_permission_codes,
        )

    def delete_role(
        self,
        *,
        role_id: int,
        actor_role_codes: list[str],
    ) -> dict:
        """软删除角色。"""
        return self._data.delete_role(
            role_id,
            actor_role_codes=actor_role_codes,
        )

    def get_role_menus(self, *, role_id: int) -> list[dict[str, Any]]:
        """读取角色菜单。"""
        return self._data.get_role_menus(role_id)

    def assign_menus(
        self,
        *,
        role_id: int,
        menu_ids: list[int],
        actor_role_codes: list[str],
        actor_permission_codes: list[str],
    ) -> dict:
        """覆盖角色菜单。"""
        return self._data.assign_role_menus(
            role_id=role_id,
            menu_ids=menu_ids,
            actor_role_codes=actor_role_codes,
            actor_permission_codes=actor_permission_codes,
        )
