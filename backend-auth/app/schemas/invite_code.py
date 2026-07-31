"""邀请码相关请求/响应 schema。"""

from __future__ import annotations

import re

from auth_utils import (
    INVITE_CODE_ALLOWED_PATTERN,
    INVITE_CODE_MAX_LENGTH,
    INVITE_CODE_MIN_LENGTH,
)
from pydantic import BaseModel, Field, field_validator


class CreateInviteCodeRequest(BaseModel):
    """创建邀请码请求。"""

    remaining: int = Field(default=1, ge=1, le=100, description="可用次数")
    expires_in_hours: int = Field(
        default=168,
        ge=1,
        le=720,
        description="过期时间(小时), 默认 7 天",
    )
    custom_code: str | None = Field(
        default=None,
        min_length=INVITE_CODE_MIN_LENGTH,
        max_length=INVITE_CODE_MAX_LENGTH,
        description="可选自定义邀请码；为空时自动生成",
    )

    @field_validator("custom_code")
    @classmethod
    def normalize_custom_code(cls, value: str | None) -> str | None:
        """统一自定义邀请码大小写并校验字符集。"""
        if value is None:
            return None
        normalized = value.strip().upper()
        if re.fullmatch(INVITE_CODE_ALLOWED_PATTERN, normalized) is None:
            raise ValueError("邀请码仅支持字母、数字、短横线和下划线")
        return normalized


class UpdateInviteCodeRequest(BaseModel):
    """更新邀请码请求（仅可修改剩余次数与过期时间）。"""

    remaining: int = Field(..., ge=1, le=100, description="可用次数")
    expires_in_hours: int = Field(
        ...,
        ge=1,
        le=720,
        description="过期时间(小时)",
    )


class InviteCodeItem(BaseModel):
    """邀请码信息。"""

    code: str
    remaining: int
    expires_at: float
    created_by: int
    created_at: float
    is_valid: bool = False
