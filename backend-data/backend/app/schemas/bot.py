"""Bot 管理相关的 Pydantic 请求/响应模型。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateBotRequest(BaseModel):
    """创建 Bot 请求体。"""

    bot_id: str = Field(..., min_length=1, max_length=64)
    name: str = Field(..., min_length=1, max_length=128)
    platform: str = Field(..., min_length=1, max_length=32)
    app_id: str = Field(..., min_length=1, max_length=128)
    app_secret: str = Field(..., min_length=1, max_length=256)
    mode: str = Field(default="test", max_length=16)


class UpdateBotRequest(BaseModel):
    """更新 Bot 请求体（字段未传则不修改）。"""

    name: str | None = Field(default=None, min_length=1, max_length=128)
    platform: str | None = Field(default=None, min_length=1, max_length=32)
    app_id: str | None = Field(default=None, min_length=1, max_length=128)
    app_secret: str | None = Field(default=None, min_length=1, max_length=256)
    mode: str | None = Field(default=None, max_length=16)
