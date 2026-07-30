"""用户域业务编排。

密码哈希留在认证服务；用户、角色、权限与头像的实际读写通过 data-client
交由 backend-data。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from api_common import InvalidCredentialsError, PermissionDeniedError
from auth_utils import (
    PROTECTED_ROLE_CODES,
    ROLE_CODE_MANAGER,
    ROLE_CODE_SUPER_ADMIN,
)
from data_client import DataClient, get_data_client

from app.core.security import hash_password, verify_password


class UserService:
    """用户管理与个人资料编排。"""

    def __init__(self, data_client: DataClient | None = None) -> None:
        self._data = data_client or get_data_client()

    def list_users(self, *, page: int = 1, page_size: int = 20) -> dict:
        """分页查询用户。"""
        return self._data.list_users(page=page, page_size=page_size)

    def create_user(
        self,
        *,
        username: str,
        password: str,
        nickname: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        role_codes: list[str] | None = None,
        actor_user_id: int,
        actor_role_codes: list[str],
        actor_permission_codes: list[str],
        is_vip: bool = False,
        vip_level: int | None = None,
        vip_expires_at: datetime | None = None,
    ) -> dict:
        """管理员创建用户。"""
        requested_roles = role_codes or []
        self._ensure_manager_assignment_allowed(
            role_codes=requested_roles,
            actor_role_codes=actor_role_codes,
        )
        return self._data.create_user(
            username=username,
            password_hash=hash_password(password),
            nickname=nickname,
            email=email,
            phone=phone,
            role_codes=requested_roles,
            actor_user_id=actor_user_id,
            actor_role_codes=actor_role_codes,
            actor_permission_codes=actor_permission_codes,
            is_vip=is_vip,
            vip_level=vip_level,
            vip_expires_at=vip_expires_at,
        )

    def assign_roles(
        self,
        *,
        user_id: int,
        role_codes: list[str],
        actor_user_id: int,
        actor_role_codes: list[str],
        actor_permission_codes: list[str],
    ) -> dict:
        """覆盖用户角色。"""
        self._ensure_manager_assignment_allowed(
            role_codes=role_codes,
            actor_role_codes=actor_role_codes,
        )
        return self._data.assign_user_roles(
            user_id=user_id,
            role_codes=role_codes,
            actor_user_id=actor_user_id,
            actor_role_codes=actor_role_codes,
            actor_permission_codes=actor_permission_codes,
        )

    def get_user_menus(self, *, user_id: int) -> list[dict[str, Any]]:
        """读取用户独立菜单。"""
        return self._data.get_user_menus(user_id)

    def assign_user_menus(
        self,
        *,
        user_id: int,
        menu_ids: list[int],
        actor_user_id: int,
        actor_role_codes: list[str],
        actor_permission_codes: list[str],
    ) -> dict:
        """覆盖用户独立菜单。"""
        return self._data.assign_user_menus(
            user_id=user_id,
            menu_ids=menu_ids,
            actor_user_id=actor_user_id,
            actor_role_codes=actor_role_codes,
            actor_permission_codes=actor_permission_codes,
        )

    def get_user_permissions(
        self,
        *,
        user_id: int,
    ) -> list[dict[str, Any]]:
        """读取用户独立权限。"""
        return self._data.get_user_permissions(user_id)

    def assign_user_permissions(
        self,
        *,
        user_id: int,
        permission_ids: list[int],
        actor_user_id: int,
        actor_role_codes: list[str],
        actor_permission_codes: list[str],
    ) -> dict:
        """覆盖用户独立权限。"""
        return self._data.assign_user_permissions(
            user_id=user_id,
            permission_ids=permission_ids,
            actor_user_id=actor_user_id,
            actor_role_codes=actor_role_codes,
            actor_permission_codes=actor_permission_codes,
        )

    def upload_avatar(
        self,
        *,
        user_id: int,
        filename: str,
        data: bytes,
        content_type: str,
    ) -> dict:
        """通过 backend-data 上传头像并保存 URL。"""
        return self._data.upload_avatar(
            user_id=user_id,
            filename=filename,
            data=data,
            content_type=content_type,
        )

    def update_profile(
        self,
        *,
        user_id: int,
        username: str,
        nickname: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        password: str | None = None,
        current_password: str | None = None,
    ) -> dict:
        """更新当前用户资料；主动改密时清除强制改密标志。"""
        if password:
            credentials = self._data.get_credentials(username)
            password_hash = credentials.get("password_hash") if credentials else None
            if (
                not current_password
                or not isinstance(password_hash, str)
                or not verify_password(current_password, password_hash)
            ):
                raise InvalidCredentialsError(message="当前密码不正确")
        return self._data.update_profile(
            user_id=user_id,
            nickname=nickname,
            email=email,
            phone=phone,
            password_hash=hash_password(password) if password else None,
        )

    @staticmethod
    def _ensure_manager_assignment_allowed(
        *,
        role_codes: list[str],
        actor_role_codes: list[str],
    ) -> None:
        """禁止分配超级管理员，并限制管理员角色的授予范围。"""
        if PROTECTED_ROLE_CODES.intersection(role_codes):
            raise PermissionDeniedError(message="超级管理员角色不可分配")
        if (
            ROLE_CODE_MANAGER in role_codes
            and ROLE_CODE_SUPER_ADMIN not in actor_role_codes
        ):
            raise PermissionDeniedError(message="仅超级管理员可以分配管理员角色")

    def reset_user_password(
        self,
        *,
        user_id: int,
        new_password: str,
        actor_user_id: int,
        actor_role_codes: list[str],
    ) -> dict:
        """管理员无复杂度限制重置密码。"""
        return self._data.reset_user_password(
            user_id=user_id,
            password_hash=hash_password(new_password),
            actor_user_id=actor_user_id,
            actor_role_codes=actor_role_codes,
        )

    def update_vip(
        self,
        *,
        user_id: int,
        is_vip: bool,
        vip_level: int | None,
        vip_expires_at: datetime | None,
        actor_user_id: int,
        actor_role_codes: list[str],
    ) -> dict:
        """更新业务 VIP 设置。"""
        return self._data.update_user_vip(
            user_id=user_id,
            is_vip=is_vip,
            vip_level=vip_level,
            vip_expires_at=vip_expires_at,
            actor_user_id=actor_user_id,
            actor_role_codes=actor_role_codes,
        )

    def update_status(
        self,
        *,
        user_id: int,
        status: int,
        actor_user_id: int,
        actor_role_codes: list[str],
    ) -> dict:
        """启用或停用用户。"""
        return self._data.update_user_status(
            user_id=user_id,
            status=status,
            actor_user_id=actor_user_id,
            actor_role_codes=actor_role_codes,
        )

    def delete_user(
        self,
        *,
        user_id: int,
        actor_user_id: int,
        actor_role_codes: list[str],
    ) -> dict:
        """按当前管理员层级软删除用户。"""
        return self._data.delete_user(
            user_id=user_id,
            actor_user_id=actor_user_id,
            actor_role_codes=actor_role_codes,
        )
