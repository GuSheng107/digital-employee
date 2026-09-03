"""Bot 管理相关的 Pydantic 请求/响应模型。"""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

Platform = Literal["feishu", "wechat"]
BotMode = Literal["test", "prod"]


class CreateBotRequest(BaseModel):
    """创建 Bot 请求体。"""

    bot_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    platform: Platform = Field(...)
    app_id: str = Field(..., min_length=1, max_length=128)
    app_secret: str = Field(..., min_length=1, max_length=256)
    mode: BotMode = Field(default="test")
    agent_id: str | None = Field(default=None)
    created_by: int | None = Field(default=None)
    parent_bot_id: int | None = Field(default=None, description="父级 Bot 主键 ID（表达部门隶属）")


class UpdateBotRequest(BaseModel):
    """更新 Bot 请求体（字段未传则不修改）。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    platform: Platform | None = Field(default=None)
    app_id: str | None = Field(default=None, min_length=1, max_length=128)
    app_secret: str | None = Field(default=None, min_length=1, max_length=256)
    mode: BotMode | None = Field(default=None)
    agent_id: str | None = Field(default=None)
    parent_bot_id: int | None = Field(default=None, description="父级 Bot 主键 ID（表达部门隶属）")
