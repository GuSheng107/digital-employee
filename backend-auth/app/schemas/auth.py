"""认证相关请求/响应 schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class LoginRequest(BaseModel):
    """登录请求。"""

    username: str = Field(..., min_length=1, max_length=64)
    password: str = Field(..., min_length=1, max_length=128)


class RegisterRequest(BaseModel):
    """注册请求。"""

    username: str = Field(..., min_length=4, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)
    invite_code: str = Field(..., min_length=1, max_length=32)


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
    status: int
    roles: list[str] = Field(default_factory=list)
    permissions: list[str] = Field(default_factory=list)
    menus: list[MenuNode] = Field(default_factory=list)
