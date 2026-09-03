"""Bot 管理路由（需要 BOT_MANAGE 权限）。

- GET    /bots         分页查询 Bot 列表
- POST   /bots         创建 Bot
- POST   /bots/{bot_id} 更新 Bot
- DELETE /bots/{bot_id} 软删除 Bot
"""

from __future__ import annotations

from typing import Literal

from api_common import ApiResponse, PermissionDeniedError, success_response
from auth_utils import ADMIN_ROLE_CODES, PermissionCode
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.deps import get_current_user, require_permission
from app.schemas.auth import UserInfo
from app.services.bot_service import BotService

router = APIRouter()

Platform = Literal["feishu", "wechat"]
BotMode = Literal["test", "prod"]


class CreateBotPayload(BaseModel):
    """创建 Bot 请求体。"""

    bot_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    platform: Platform = Field(...)
    app_id: str = Field(..., min_length=1, max_length=128)
    app_secret: str = Field(..., min_length=1, max_length=256)
    mode: BotMode = Field(default="test")
    agent_id: str | None = Field(default=None)
    parent_bot_id: int | None = Field(default=None, description="父级 Bot 主键 ID（表达部门隶属）")


class UpdateBotPayload(BaseModel):
    """更新 Bot 请求体（字段未传则不修改）。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    platform: Platform | None = Field(default=None)
    app_id: str | None = Field(default=None, min_length=1, max_length=128)
    app_secret: str | None = Field(default=None, min_length=1, max_length=256)
    mode: BotMode | None = Field(default=None)
    agent_id: str | None = Field(default=None)
    parent_bot_id: int | None = Field(default=None, description="父级 Bot 主键 ID（表达部门隶属）")


@router.get(
    "",
    response_model=ApiResponse,
    dependencies=[
        Depends(
            require_permission(
                PermissionCode.BOT_MANAGE,
                PermissionCode.BOT_READONLY,
            )
        )
    ],
)
def list_bots(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    current_user: UserInfo = Depends(get_current_user),
) -> dict:
    """分页查询 Bot 列表（管理员查全量，普通用户仅查自己创建的 Bot）。"""
    service = BotService()
    is_admin = bool(ADMIN_ROLE_CODES.intersection(current_user.roles))
    created_by = None if is_admin else current_user.id
    return success_response(
        service.list_bots(page=page, page_size=page_size, created_by=created_by)
    )


@router.post(
    "",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.BOT_MANAGE))],
)
def create_bot(
    payload: CreateBotPayload,
    current_user: UserInfo = Depends(get_current_user),
) -> dict:
    """创建 Bot（自动绑定当前创建者用户 ID）。"""
    service = BotService()
    result = service.create_bot(
        bot_id=payload.bot_id,
        name=payload.name,
        platform=payload.platform,
        app_id=payload.app_id,
        app_secret=payload.app_secret,
        mode=payload.mode,
        agent_id=payload.agent_id,
        created_by=current_user.id,
        parent_bot_id=payload.parent_bot_id,
    )
    return success_response(result)


@router.post(
    "/{bot_id}",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.BOT_MANAGE))],
)
def update_bot(
    bot_id: str,
    payload: UpdateBotPayload,
    current_user: UserInfo = Depends(get_current_user),
) -> dict:
    """更新 Bot 配置（管理员可修改任意 Bot，普通用户仅能修改自己创建的 Bot）。"""
    service = BotService()
    is_admin = bool(ADMIN_ROLE_CODES.intersection(current_user.roles))
    if not is_admin:
        target_bot = service.get_bot(bot_id=bot_id)
        if target_bot.get("created_by") != current_user.id:
            raise PermissionDeniedError(message="无权修改非本人创建的机器人")
    result = service.update_bot(
        bot_id=bot_id,
        **payload.model_dump(exclude_unset=True),
    )
    return success_response(result)


@router.delete(
    "/{bot_id}",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.BOT_MANAGE))],
)
def delete_bot(
    bot_id: str,
    current_user: UserInfo = Depends(get_current_user),
) -> dict:
    """软删除 Bot（管理员可删除任意 Bot，普通用户仅能删除自己创建的 Bot）。"""
    service = BotService()
    is_admin = bool(ADMIN_ROLE_CODES.intersection(current_user.roles))
    if not is_admin:
        target_bot = service.get_bot(bot_id=bot_id)
        if target_bot.get("created_by") != current_user.id:
            raise PermissionDeniedError(message="无权删除非本人创建的机器人")
    result = service.delete_bot(bot_id=bot_id)
    return success_response(result)
