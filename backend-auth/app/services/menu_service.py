"""菜单管理编排，实际数据操作由 backend-data 完成。"""

from __future__ import annotations

from typing import Any

from data_client import DataClient, get_data_client


class MenuService:
    """菜单管理代理。"""

    def __init__(self, data_client: DataClient | None = None) -> None:
        self._data = data_client or get_data_client()

    def list_menus(self) -> list[dict[str, Any]]:
        """列出菜单。"""
        return self._data.list_menus()

    def create_menu(self, **payload: Any) -> dict:
        """创建菜单。"""
        return self._data.create_menu(payload)

    def update_menu(self, *, menu_id: int, **payload: Any) -> dict:
        """更新菜单。"""
        return self._data.update_menu(menu_id=menu_id, payload=payload)

    def delete_menu(self, *, menu_id: int) -> dict:
        """软删除菜单。"""
        return self._data.delete_menu(menu_id)
