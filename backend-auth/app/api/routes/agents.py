"""Agent 管理路由（需要 AGENT_MANAGE 权限）。

- GET    /agents         分页查询 Agent 列表
- POST   /agents         创建 Agent
- POST   /agents/{agent_id} 更新 Agent
- DELETE /agents/{agent_id} 软删除 Agent
"""

from __future__ import annotations

from api_common import ApiResponse, PermissionDeniedError, success_response
from auth_utils import ADMIN_ROLE_CODES, PermissionCode
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, require_permission
from app.schemas.auth import UserInfo
from app.services.agent_service import AgentService

router = APIRouter()


class CreateAgentPayload(BaseModel):
    """创建 Agent 请求体。"""

    agent_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    status: int = Field(default=1)


class UpdateAgentPayload(BaseModel):
    """更新 Agent 请求体。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    status: int | None = Field(default=None)


@router.get(
    "",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.AGENT_MANAGE))],
)
def list_agents(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: UserInfo = Depends(get_current_user),
) -> dict:
    """分页查询 Agent 列表（管理员查全量，普通用户仅查自己创建的 Agent）。"""
    service = AgentService()
    is_admin = bool(ADMIN_ROLE_CODES.intersection(current_user.roles))
    created_by = None if is_admin else current_user.id
    return success_response(
        service.list_agents(page=page, page_size=page_size, created_by=created_by)
    )


@router.post(
    "",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.AGENT_MANAGE))],
)
def create_agent(
    payload: CreateAgentPayload,
    current_user: UserInfo = Depends(get_current_user),
) -> dict:
    """创建 Agent（自动绑定当前创建者用户 ID）。"""
    service = AgentService()
    result = service.create_agent(
        agent_id=payload.agent_id,
        name=payload.name,
        status=payload.status,
        created_by=current_user.id,
    )
    return success_response(result)


@router.post(
    "/{agent_id}",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.AGENT_MANAGE))],
)
def update_agent(
    agent_id: str,
    payload: UpdateAgentPayload,
    current_user: UserInfo = Depends(get_current_user),
) -> dict:
    """更新 Agent 配置（普通用户仅能修改自己创建的 Agent）。"""
    service = AgentService()
    is_admin = bool(ADMIN_ROLE_CODES.intersection(current_user.roles))
    if not is_admin:
        target_agent = service.get_agent(agent_id=agent_id)
        if target_agent.get("created_by") != current_user.id:
            raise PermissionDeniedError(message="无权修改非本人创建的 Agent")
    result = service.update_agent(
        agent_id=agent_id,
        **payload.model_dump(exclude_unset=True),
    )
    return success_response(result)


@router.delete(
    "/{agent_id}",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.AGENT_MANAGE))],
)
def delete_agent(
    agent_id: str,
    current_user: UserInfo = Depends(get_current_user),
) -> dict:
    """软删除 Agent（普通用户仅能删除自己创建的 Agent）。"""
    service = AgentService()
    is_admin = bool(ADMIN_ROLE_CODES.intersection(current_user.roles))
    if not is_admin:
        target_agent = service.get_agent(agent_id=agent_id)
        if target_agent.get("created_by") != current_user.id:
            raise PermissionDeniedError(message="无权删除非本人创建的 Agent")
    result = service.delete_agent(agent_id=agent_id)
    return success_response(result)
