"""Bot 管理编排，实际数据操作由 backend-data 完成。"""

from __future__ import annotations

from typing import Any

from data_client import DataClient, get_data_client


class BotService:
    """Bot 管理代理。"""

    def __init__(self, data_client: DataClient | None = None) -> None:
        self._data = data_client or get_data_client()

    def list_bots(self, *, page: int, page_size: int) -> dict[str, Any]:
        """分页查询 Bot 列表。"""
        return self._data.list_bots(page=page, page_size=page_size)

    def create_bot(self, **payload: Any) -> dict[str, Any]:
        """创建 Bot。"""
        return self._data.create_bot(**payload)

    def update_bot(self, *, bot_id: str, **fields: Any) -> dict[str, Any]:
        """更新 Bot 配置。"""
        return self._data.update_bot(bot_id=bot_id, **fields)

    def delete_bot(self, *, bot_id: str) -> dict[str, Any]:
        """软删除 Bot。"""
        return self._data.delete_bot(bot_id)
