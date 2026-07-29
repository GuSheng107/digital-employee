"""backend-auth 调用 backend-data 的内部身份域契约。"""

from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel, Field, model_validator


NON_NULLABLE_MENU_UPDATE_FIELDS = frozenset(
    {"parent_id", "menu_type", "title", "sort", "visible"}
)


class RegisterIdentityRequest(BaseModel):
    """创建注册用户并签发初始会话。"""

    username: str = Field(..., min_length=4, max_length=64)
    password_hash: str = Field(..., min_length=1, max_length=255)
    email: str = Field(..., min_length=1, max_length=128)
    phone: str = Field(..., min_length=1, max_length=32)
    invite_code: str = Field(..., min_length=1, max_length=32)
    access_token: str = Field(..., min_length=1)
    refresh_token: str = Field(..., min_length=1)


class UsernameIdentityRequest(BaseModel):
    """按用户名读取内部凭据。"""

    username: str = Field(..., min_length=1, max_length=64)


class AccessTokenIdentityRequest(BaseModel):
    """按 access token 读取可信用户上下文。"""

    access_token: str = Field(..., min_length=1)
    include_menus: bool = True


class CompleteLoginRequest(BaseModel):
    """完成登录审计与单会话 token 写入。"""

    user_id: int = Field(..., ge=1)
    client_ip: str | None = Field(default=None, max_length=64)
    access_token: str = Field(..., min_length=1)
    refresh_token: str = Field(..., min_length=1)


class RefreshIdentitySessionRequest(BaseModel):
    """轮换双 token。"""

    refresh_token: str = Field(..., min_length=1)
    new_access_token: str = Field(..., min_length=1)
    new_refresh_token: str = Field(..., min_length=1)


class LogoutIdentitySessionRequest(BaseModel):
    """撤销当前会话。"""

    access_token: str = Field(..., min_length=1)
    refresh_token: str | None = None


class ConsumeIdentityRateLimitRequest(BaseModel):
    """消费认证接口的固定窗口限流计数。"""

    bucket: str = Field(..., pattern=r"^[a-z0-9_-]+$", max_length=32)
    identifier_hash: str = Field(..., pattern=r"^[a-f0-9]{64}$")
    limit: int = Field(..., ge=1, le=10000)
    window_seconds: int = Field(..., ge=1, le=86400)


class ResetIdentityRateLimitRequest(BaseModel):
    """清除登录成功后的账号维度限流桶。"""

    bucket: str = Field(..., pattern=r"^[a-z0-9_-]+$", max_length=32)
    identifier_hash: str = Field(..., pattern=r"^[a-f0-9]{64}$")


class VerifyIdentityCaptchaRequest(BaseModel):
    """消费并校验一次性算术验证码。"""

    captcha_id: str = Field(
        ...,
        min_length=20,
        max_length=64,
        pattern=r"^[A-Za-z0-9_-]+$",
    )
    captcha_answer: str = Field(..., min_length=1, max_length=3, pattern=r"^\d+$")


class CreateIdentityUserRequest(BaseModel):
    """管理员创建用户的数据写入请求。"""

    username: str = Field(..., min_length=4, max_length=64)
    password_hash: str = Field(..., min_length=1, max_length=255)
    nickname: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    role_codes: list[str] = Field(default_factory=list)
    actor_user_id: int = Field(..., ge=1)
    actor_role_codes: list[str] = Field(default_factory=list)
    actor_permission_codes: list[str] = Field(default_factory=list)
    is_vip: bool = False
    vip_level: int | None = None
    vip_expires_at: datetime | None = None


class UpdateIdentityProfileRequest(BaseModel):
    """个人资料数据写入请求。"""

    nickname: str | None = Field(default=None, max_length=64)
    email: str | None = Field(default=None, max_length=128)
    phone: str | None = Field(default=None, max_length=32)
    password_hash: str | None = Field(default=None, max_length=255)


class ResetIdentityPasswordRequest(BaseModel):
    """管理员重置密码哈希。"""

    password_hash: str = Field(..., min_length=1, max_length=255)
    actor_user_id: int = Field(..., ge=1)
    actor_role_codes: list[str] = Field(default_factory=list)


class UpdateIdentityVipRequest(BaseModel):
    """更新 VIP 配置。"""

    is_vip: bool
    vip_level: int | None = None
    vip_expires_at: datetime | None = None
    actor_user_id: int = Field(..., ge=1)
    actor_role_codes: list[str] = Field(default_factory=list)


class UpdateIdentityStatusRequest(BaseModel):
    """更新用户状态。"""

    status: int = Field(..., ge=0, le=1)
    actor_user_id: int = Field(..., ge=1)
    actor_role_codes: list[str] = Field(default_factory=list)


class DeleteIdentityUserRequest(BaseModel):
    """删除用户时携带的可信操作者上下文。"""

    actor_user_id: int = Field(..., ge=1)
    actor_role_codes: list[str] = Field(default_factory=list)


class RoleCodesRequest(BaseModel):
    """角色代码集合。"""

    role_codes: list[str] = Field(default_factory=list)
    actor_user_id: int = Field(..., ge=1)
    actor_role_codes: list[str] = Field(default_factory=list)
    actor_permission_codes: list[str] = Field(default_factory=list)


class IdsRequest(BaseModel):
    """通用 ID 集合。"""

    ids: list[int] = Field(default_factory=list)


class ManagedIdsRequest(IdsRequest):
    """携带可信操作者上下文的 ID 集合。"""

    actor_user_id: int = Field(..., ge=1)
    actor_role_codes: list[str] = Field(default_factory=list)
    actor_permission_codes: list[str] = Field(default_factory=list)


class CreateIdentityRoleRequest(BaseModel):
    """创建角色。"""

    code: str = Field(..., min_length=2, max_length=64)
    name: str = Field(..., min_length=1, max_length=64)
    description: str = Field(default="", max_length=255)
    menu_ids: list[int] = Field(default_factory=list)
    actor_role_codes: list[str] = Field(default_factory=list)
    actor_permission_codes: list[str] = Field(default_factory=list)


class UpdateIdentityRoleRequest(BaseModel):
    """更新角色。"""

    name: str | None = Field(default=None, min_length=1, max_length=64)
    description: str | None = Field(default=None, max_length=255)
    menu_ids: list[int] | None = None
    actor_role_codes: list[str] = Field(default_factory=list)
    actor_permission_codes: list[str] = Field(default_factory=list)


class DeleteIdentityRoleRequest(BaseModel):
    """删除角色时携带可信操作者上下文。"""

    actor_role_codes: list[str] = Field(default_factory=list)


class ManageIdentityRoleMenusRequest(IdsRequest):
    """维护角色菜单时携带可信操作者上下文。"""

    actor_role_codes: list[str] = Field(default_factory=list)
    actor_permission_codes: list[str] = Field(default_factory=list)


class CreateIdentityMenuRequest(BaseModel):
    """创建菜单。"""

    parent_id: int = Field(default=0, ge=0)
    menu_type: int = Field(..., ge=1, le=3)
    title: str = Field(..., min_length=1, max_length=64)
    path: str | None = Field(default=None, max_length=255)
    component: str | None = Field(default=None, max_length=255)
    icon: str | None = Field(default=None, max_length=64)
    permission: str | None = Field(default=None, max_length=128)
    sort: int = Field(default=0, ge=0)
    visible: bool = True


class UpdateIdentityMenuRequest(BaseModel):
    """更新菜单。"""

    parent_id: int | None = Field(default=None, ge=0)
    menu_type: int | None = Field(default=None, ge=1, le=3)
    title: str | None = Field(default=None, min_length=1, max_length=64)
    path: str | None = Field(default=None, max_length=255)
    component: str | None = Field(default=None, max_length=255)
    icon: str | None = Field(default=None, max_length=64)
    permission: str | None = Field(default=None, max_length=128)
    sort: int | None = Field(default=None, ge=0)
    visible: bool | None = None

    @model_validator(mode="after")
    def reject_explicit_null_for_required_columns(
        self,
    ) -> UpdateIdentityMenuRequest:
        """内部更新协议同样拒绝清空非空菜单字段。"""
        invalid_fields = sorted(
            field_name
            for field_name in self.model_fields_set
            if (
                field_name in NON_NULLABLE_MENU_UPDATE_FIELDS
                and getattr(self, field_name) is None
            )
        )
        if invalid_fields:
            raise ValueError(f"菜单字段不能设为空：{', '.join(invalid_fields)}")
        return self


class CreateIdentityInviteCodeRequest(BaseModel):
    """创建随机或自定义邀请码。"""

    remaining: int = Field(default=1, ge=1, le=100)
    expires_in_hours: int = Field(default=168, ge=1, le=720)
    created_by: int = Field(..., ge=1)
    custom_code: str | None = Field(default=None, min_length=4, max_length=32)
