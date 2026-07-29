"""用户管理相关请求/响应 schema。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator

from app.core.validation import (
    PASSWORD_MAX_LENGTH,
    PASSWORD_MIN_LENGTH,
    normalize_email_address,
    normalize_phone_number,
    validate_admin_reset_password,
    validate_password_complexity,
)


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
    vip_expires_at: str | None = None
    roles: list[str] = Field(default_factory=list)
    last_login_at: str | None = None
    last_login_ip: str | None = None
    created_at: str | None = None
    updated_at: str | None = None


class UserListResponse(BaseModel):
    """用户列表分页响应。"""

    total: int
    page: int
    page_size: int
    items: list[UserListItem]


class CreateUserRequest(BaseModel):
    """管理员创建用户请求。"""

    username: str = Field(..., min_length=4, max_length=64)
    password: str = Field(
        ...,
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
    )
    nickname: str | None = Field(default=None, max_length=64)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    role_codes: list[str] = Field(default_factory=list)
    is_vip: bool = False
    vip_level: int | None = None
    vip_expires_at: datetime | None = None

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        """校验管理员创建用户时的初始密码复杂度。"""
        return validate_password_complexity(value)

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        """统一管理员创建用户时的邮箱存储形式。"""
        return normalize_email_address(value)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        """校验非空手机号并转为 E.164。"""
        return normalize_phone_number(value) if value else value


class AssignRolesRequest(BaseModel):
    """分配用户角色请求。"""

    role_codes: list[str] = Field(default_factory=list)


class UpdateProfileRequest(BaseModel):
    """更新个人信息请求。

    ``password`` 可选；为空表示不修改密码，非空则同时更新密码（需配合当前
    用户登录态，仅用于个人信息页自助修改）。
    """

    nickname: str | None = Field(default=None, max_length=64)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    password: str | None = Field(
        default=None,
        min_length=PASSWORD_MIN_LENGTH,
        max_length=PASSWORD_MAX_LENGTH,
    )

    @field_validator("password")
    @classmethod
    def validate_password(cls, value: str | None) -> str | None:
        """校验用户主动修改密码时的复杂度。"""
        return validate_password_complexity(value) if value else value

    @field_validator("email", mode="before")
    @classmethod
    def normalize_email(cls, value: str | None) -> str | None:
        """统一个人资料邮箱的存储形式。"""
        return normalize_email_address(value)

    @field_validator("phone")
    @classmethod
    def validate_phone(cls, value: str | None) -> str | None:
        """校验非空手机号并转为 E.164。"""
        return normalize_phone_number(value) if value else value


class ResetPasswordRequest(BaseModel):
    """管理员重置用户密码请求。"""

    new_password: str = Field(..., min_length=1, max_length=PASSWORD_MAX_LENGTH)

    @field_validator("new_password")
    @classmethod
    def validate_password(cls, value: str) -> str:
        """管理员重置不应用普通用户密码复杂度规则。"""
        return validate_admin_reset_password(value)


class UpdateVipRequest(BaseModel):
    """更新用户 VIP 设置。"""

    is_vip: bool
    vip_level: int | None = None
    vip_expires_at: datetime | None = None


class UpdateUserStatusRequest(BaseModel):
    """更新用户启停状态。"""

    status: int = Field(..., ge=0, le=1)


class AssignUserMenusRequest(BaseModel):
    """分配用户独立菜单请求（覆盖式）。"""

    menu_ids: list[int] = Field(default_factory=list)


class AssignUserPermissionsRequest(BaseModel):
    """分配用户独立权限请求（覆盖式）。"""

    permission_ids: list[int] = Field(default_factory=list)
