"""Bot 管理路由（需要 BOT_MANAGE 权限）。

- GET    /bots         分页查询 Bot 列表
- POST   /bots         创建 Bot
- PUT    /bots/{bot_id} 更新 Bot
- DELETE /bots/{bot_id} 软删除 Bot
"""

from __future__ import annotations

from api_common import ApiResponse, success_response
from auth_utils import PermissionCode
from fastapi import APIRouter, Depends, Query
from pydantic import BaseModel, Field

from app.api.deps import require_permission
from app.services.bot_service import BotService

router = APIRouter()


class CreateBotPayload(BaseModel):
    """创建 Bot 请求体。"""

    bot_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    platform: str = Field(..., min_length=1, max_length=32)
    app_id: str = Field(..., min_length=1, max_length=128)
    app_secret: str = Field(..., min_length=1, max_length=256)
    mode: str = Field(default="test", max_length=16)


class UpdateBotPayload(BaseModel):
    """更新 Bot 请求体。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    platform: str | None = Field(default=None, min_length=1, max_length=32)
    app_id: str | None = Field(default=None, min_length=1, max_length=128)
    app_secret: str | None = Field(default=None, min_length=1, max_length=256)
    mode: str | None = Field(default=None, max_length=16)


@router.get(
    "",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.BOT_MANAGE))],
)
def list_bots(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    """分页查询 Bot 列表。"""
    service = BotService()
    return success_response(service.list_bots(page=page, page_size=page_size))


@router.post(
    "",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.BOT_MANAGE))],
)
def create_bot(payload: CreateBotPayload) -> dict:
    """创建 Bot。"""
    service = BotService()
    result = service.create_bot(
        bot_id=payload.bot_id,
        name=payload.name,
        platform=payload.platform,
        app_id=payload.app_id,
        app_secret=payload.app_secret,
        mode=payload.mode,
    )
    return success_response(result)


@router.put(
    "/{bot_id}",
    response_model=ApiResponse,
    dependencies=[Depends(require_permission(PermissionCode.BOT_MANAGE))],
)
def update_bot(bot_id: str, payload: UpdateBotPayload) -> dict:
    """更新 Bot 配置。"""
    service = BotService()
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
def delete_bot(bot_id: str) -> dict:
    """软删除 Bot。"""
    service = BotService()
    result = service.delete_bot(bot_id=bot_id)
    return success_response(result)
