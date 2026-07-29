"""权限目录编排，实际数据读取由 backend-data 完成。"""

from __future__ import annotations

from typing import Any

from data_client import DataClient, get_data_client


class PermissionService:
    """权限码目录代理。"""

    def __init__(self, data_client: DataClient | None = None) -> None:
        self._data = data_client or get_data_client()

    def list_permissions(self) -> list[dict[str, Any]]:
        """列出权限码目录。"""
        return self._data.list_permissions()
