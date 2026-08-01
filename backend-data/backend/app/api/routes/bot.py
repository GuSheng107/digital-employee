"""Bot 管理 API 路由。

- GET    /bots         分页查询 Bot 列表（前端管理页用）
- GET    /bots/active  查询全部活跃 Bot（Gateway 启动拉取用）
- POST   /bots         创建 Bot
- POST   /bots/{bot_id} 更新 Bot
- DELETE /bots/{bot_id} 软删除 Bot
"""

from __future__ import annotations

from api_common import ApiResponse, success_response
from fastapi import APIRouter, Query

from app.schemas.bot import CreateBotRequest, UpdateBotRequest
from app.services.bot_service import BotService

router = APIRouter()


@router.get("", response_model=ApiResponse)
def list_bots(
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
) -> dict:
    """分页查询 Bot 列表（app_secret 脱敏）。"""
    service = BotService()
    return success_response(service.list_bots(page=page, page_size=page_size))


@router.get("/active", response_model=ApiResponse)
def list_active_bots() -> dict:
    """查询全部活跃 Bot（含 app_secret 明文，仅限内部服务调用）。"""
    service = BotService()
    return success_response(service.list_active_bots())


@router.post("", response_model=ApiResponse)
def create_bot(payload: CreateBotRequest) -> dict:
    """创建 Bot。"""
    service = BotService()
    result = service.create_bot(
        bot_id=payload.bot_id,
        name=payload.name,
        platform=payload.platform,
        app_id=payload.app_id,
        app_secret=payload.app_secret,
        mode=payload.mode,
        created_by=payload.created_by,
    )
    return success_response(result)


@router.post("/{bot_id}", response_model=ApiResponse)
def update_bot(bot_id: str, payload: UpdateBotRequest) -> dict:
    """更新 Bot 配置（字段未传则不修改）。"""
    service = BotService()
    result = service.update_bot(
        bot_id=bot_id,
        **payload.model_dump(exclude_unset=True),
    )
    return success_response(result)


@router.delete("/{bot_id}", response_model=ApiResponse)
def delete_bot(bot_id: str) -> dict:
    """软删除 Bot。"""
    service = BotService()
    result = service.delete_bot(bot_id=bot_id)
    return success_response(result)
