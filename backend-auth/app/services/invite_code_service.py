"""邀请码管理编排，Redis 读写由 backend-data 完成。"""

from __future__ import annotations

from typing import Any

from data_client import DataClient, get_data_client


class InviteCodeService:
    """邀请码管理代理。"""

    def __init__(self, data_client: DataClient | None = None) -> None:
        self._data = data_client or get_data_client()

    def create(
        self,
        *,
        remaining: int,
        expires_in_hours: int,
        created_by: int,
        custom_code: str | None,
    ) -> dict:
        """创建随机或自定义邀请码。"""
        return self._data.create_invite_code(
            remaining=remaining,
            expires_in_hours=expires_in_hours,
            created_by=created_by,
            custom_code=custom_code,
        )

    def list_page(self, *, page: int, page_size: int) -> dict[str, Any]:
        """分页列出邀请码。"""
        return self._data.list_invite_codes(page=page, page_size=page_size)
