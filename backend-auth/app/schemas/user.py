"""用户管理相关请求/响应 schema。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class UserListItem(BaseModel):
    """用户列表项。"""

    id: int
    username: str
    nickname: str | None = None
    email: str | None = None
    phone: str | None = None
    avatar_url: str | None = None
    status: int
    is_vip: bool
    vip_level: int | None = 0
    vip_level_display: str = "普通用户"
    roles: list[str] = Field(default_factory=list)
    last_login_at: str | None = None
    created_at: str | None = None


class UserListResponse(BaseModel):
    """用户列表分页响应。"""

    total: int
    page: int
    page_size: int
    items: list[UserListItem]


class CreateUserRequest(BaseModel):
    """管理员创建用户请求。"""

    username: str = Field(..., min_length=4, max_length=64)
    password: str = Field(..., min_length=8, max_length=128)
    nickname: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    role_codes: list[str] = Field(default_factory=list)


class AssignRolesRequest(BaseModel):
    """分配用户角色请求。"""

    role_codes: list[str] = Field(default_factory=list)


class UpdateProfileRequest(BaseModel):
    """更新个人信息请求。

    ``password`` 可选；为空表示不修改密码，非空则同时更新密码（需配合当前
    用户登录态，仅用于个人信息页自助修改）。
    """

    nickname: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    password: str | None = Field(default=None, min_length=8, max_length=128)


class ResetPasswordRequest(BaseModel):
    """管理员重置用户密码请求。"""

    new_password: str = Field(..., min_length=8, max_length=128)


class AssignUserMenusRequest(BaseModel):
    """分配用户独立菜单请求（覆盖式）。"""

    menu_ids: list[int] = Field(default_factory=list)


class AssignUserPermissionsRequest(BaseModel):
    """分配用户独立权限请求（覆盖式）。"""

    permission_ids: list[int] = Field(default_factory=list)
