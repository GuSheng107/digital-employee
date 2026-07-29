"""认证相关请求/响应 schema。"""

from __future__ import annotations

import re
from datetime import datetime

from auth_utils import (
    INVITE_CODE_ALLOWED_PATTERN,
    INVITE_CODE_MAX_LENGTH,
    INVITE_CODE_MIN_LENGTH,
)
from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.validation import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    normalize_email_address,
    normalize_phone_number,
    validate_password_complexity,
)


class LoginRequest(BaseModel):
    """登录请求。"""

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)
    captcha_id: str = Field(..., min_length=20, max_length=64)
    captcha_answer: str = Field(..., min_length=1, max_length=3, pattern=r"^\d+$")


class CaptchaChallenge(BaseModel):
    """前端可展示的算术图片验证码挑战。"""

    captcha_id: str
    image_data_url: str
    expires_in: int


class RegisterRequest(BaseModel):
    """注册请求。"""

    username: str = Field(..., min_length=4, max_length=64)
    password: str = Field(
        ...,
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
    )
    email: EmailStr
    phone: str = Field(..., min_length=1, max_length=32)
    invite_code: str = Field(
        ...,
        min_length=INVITE_CODE_MIN_LENGTH,
        max_length=INVITE_CODE_MAX_LENGTH,
    )
    captcha_id: str = Field(..., min_length=20, max_length=64)
    captcha_answer: str = Field(..., min_length=1, max_length=3, pattern=r"^\d+$")

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        """校验注册密码复杂度。"""
        return validate_password_complexity(value)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str) -> str:
        """统一注册邮箱的存储形式。"""
        return normalize_email_address(value) or ""

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str) -> str:
        """校验手机号并转为 E.164。"""
        return normalize_phone_number(value)

    @field_validator("invite_code")
    @classmethod
    def normalize_invite_code(cls, value: str) -> str:
        """统一邀请码大小写并校验字符集。"""
        normalized = value.strip().upper()
        if re.fullmatch(INVITE_CODE_ALLOWED_PATTERN, normalized) is None:
            raise ValueError("邀请码仅支持字母、数字、短横线和下划线")
        return normalized


class TokenPair(BaseModel):
    """双 token 响应。

    access_token 短 TTL，用于业务接口鉴权；
    refresh_token 长 TTL，用于换取新的 access_token。
    """

    access_token: str
    refresh_token: str
    access_expires_in: int
    refresh_expires_in: int
    token_type: str = "Bearer"
    user_id: int
    must_change_password: bool = False


class RefreshRequest(BaseModel):
    """刷新 token 请求。"""

    refresh_token: str = Field(..., min_length=1)


class LogoutRequest(BaseModel):
    """登出请求（可选，前端仅依赖 Authorization 头也可）。"""

    refresh_token: str | None = Field(default=None)


class MenuNode(BaseModel):
    """菜单树节点。"""

    id: int
    parent_id: int
    menu_type: int
    title: str
    path: str | None = None
    component: str | None = None
    icon: str | None = None
    permission: str | None = None
    sort: int = 0
    visible: bool = True
    children: list[MenuNode] = Field(default_factory=list)


class UserInfo(BaseModel):
    """当前登录用户信息。"""

    id: int
    username: str
    nickname: str | None = None
    email: str | None = None
    phone: str | None = None
    avatar_url: str | None = None
    is_vip: bool
    vip_level: int | None = 0
    vip_level_display: str = "普通用户"
    vip_expires_at: datetime | None = None
    status: int
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    menus: list[MenuNode] = Field(default_factory=list)
    must_change_password: bool = False
