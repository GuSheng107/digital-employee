"""Agent 请求与响应 Schema 定义。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field


class CreateAgentRequest(BaseModel):
    """创建 Agent 请求体。"""

    agent_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    status: int = Field(default=1)
    created_by: int | None = Field(default=None)


class UpdateAgentRequest(BaseModel):
    """更新 Agent 请求体。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    status: int | None = Field(default=None)


class AgentResponse(BaseModel):
    """Agent 响应对象。"""

    id: int
    agent_id: str
    name: str
    status: int
    created_by: int | None = None
    created_by_name: str | None = None
    created_at: datetime | None = None
    updated_at: datetime | None = None
