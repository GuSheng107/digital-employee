"""Agent 管理路由（仅限内部服务调用或无锁只读访问）。

- GET    /agents          分页查询 Agent 列表
- GET    /agents/{agent_id} 获取 Agent 详情
- POST   /agents          创建 Agent
- POST   /agents/{agent_id} 更新 Agent
- DELETE /agents/{agent_id} 软删除 Agent
"""

from __future__ import annotations

from api_common import ApiResponse, success_response
from fastapi import APIRouter, Query

from app.schemas.agent import CreateAgentRequest, UpdateAgentRequest
from app.services.agent_service import AgentService

router = APIRouter()


@router.get("", response_model=ApiResponse)
def list_agents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    created_by: int | None = Query(default=None),
) -> dict:
    """分页查询 Agent 列表。"""
    service = AgentService()
    return success_response(
        service.list_agents(page=page, page_size=page_size, created_by=created_by)
    )


@router.get("/{agent_id}", response_model=ApiResponse)
def get_agent(agent_id: str) -> dict:
    """获取单条 Agent 详情。"""
    service = AgentService()
    return success_response(service.get_agent(agent_id=agent_id))


@router.post("", response_model=ApiResponse)
def create_agent(payload: CreateAgentRequest) -> dict:
    """创建 Agent。"""
    service = AgentService()
    result = service.create_agent(
        agent_id=payload.agent_id,
        name=payload.name,
        status=payload.status,
        created_by=payload.created_by,
    )
    return success_response(result)


@router.post("/{agent_id}", response_model=ApiResponse)
def update_agent(agent_id: str, payload: UpdateAgentRequest) -> dict:
    """更新 Agent 配置。"""
    service = AgentService()
    result = service.update_agent(
        agent_id=agent_id,
        **payload.model_dump(exclude_unset=True),
    )
    return success_response(result)


@router.delete("/{agent_id}", response_model=ApiResponse)
def delete_agent(agent_id: str) -> dict:
    """软删除 Agent。"""
    service = AgentService()
    result = service.delete_agent(agent_id=agent_id)
    return success_response(result)
