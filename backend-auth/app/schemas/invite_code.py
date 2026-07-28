"""邀请码相关请求/响应 schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class CreateInviteCodeRequest(BaseModel):
    """创建邀请码请求。"""

    remaining: int = Field(default=1, ge=1, le=100, description="可用次数")
    expires_in_hours: int = Field(
        default=168,
        ge=1,
        le=720,
        description="过期时间(小时), 默认 7 天",
    )


class InviteCodeItem(BaseModel):
    """邀请码信息。"""

    code: str
    remaining: int
    expires_at: float
    created_by: int
    created_at: float
    is_valid: bool = False
