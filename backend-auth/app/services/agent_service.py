"""Agent 管理编排，实际数据操作由 backend-data 完成。"""

from __future__ import annotations

from typing import Any

from data_client import DataClient, get_data_client


class AgentService:
    """Agent 管理代理。"""

    def __init__(self, data_client: DataClient | None = None) -> None:
        self._data = data_client or get_data_client()

    def list_agents(
        self,
        *,
        page: int,
        page_size: int,
        created_by: int | None = None,
    ) -> dict[str, Any]:
        """分页查询 Agent 列表。"""
        return self._data.list_agents(
            page=page, page_size=page_size, created_by=created_by
        )

    def get_agent(self, *, agent_id: str) -> dict[str, Any]:
        """获取单个 Agent 详情。"""
        return self._data.get_agent(agent_id=agent_id)

    def create_agent(self, **payload: Any) -> dict[str, Any]:
        """创建 Agent。"""
        return self._data.create_agent(**payload)

    def update_agent(self, *, agent_id: str, **fields: Any) -> dict[str, Any]:
        """更新 Agent 配置。"""
        return self._data.update_agent(agent_id=agent_id, **fields)

    def delete_agent(self, *, agent_id: str) -> dict[str, Any]:
        """软删除 Agent。"""
        return self._data.delete_agent(agent_id)
