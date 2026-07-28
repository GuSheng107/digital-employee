"""认证相关请求/响应 schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录请求。"""

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


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


class RefreshRequest(BaseModel):
    """刷新 token 请求。"""

    refresh_token: str = Field(..., min_length=1)


class LogoutRequest(BaseModel):
    """登出请求（可选，前端仅依赖 Authorization 头也可）。"""

    refresh_token: str | None = Field(default=None)


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
    status: int
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
