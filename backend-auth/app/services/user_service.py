"""用户域业务编排。

密码哈希留在认证服务；用户、角色、权限与头像的实际读写通过 data-client
交由 backend-data。
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from data_client import DataClient, get_data_client

from app.core.security import hash_password


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
        is_vip: bool = False,
        vip_level: int | None = None,
        vip_expires_at: datetime | None = None,
    ) -> dict:
        """管理员创建用户。"""
        return self._data.create_user(
            username=username,
            password_hash=hash_password(password),
            nickname=nickname,
            email=email,
            phone=phone,
            role_codes=role_codes or [],
            is_vip=is_vip,
            vip_level=vip_level,
            vip_expires_at=vip_expires_at,
        )

    def assign_roles(self, *, user_id: int, role_codes: list[str]) -> dict:
        """覆盖用户角色。"""
        return self._data.assign_user_roles(
            user_id=user_id,
            role_codes=role_codes,
        )

    def get_user_menus(self, *, user_id: int) -> list[dict[str, Any]]:
        """读取用户独立菜单。"""
        return self._data.get_user_menus(user_id)

    def assign_user_menus(
        self,
        *,
        user_id: int,
        menu_ids: list[int],
    ) -> dict:
        """覆盖用户独立菜单。"""
        return self._data.assign_user_menus(
            user_id=user_id,
            menu_ids=menu_ids,
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
    ) -> dict:
        """覆盖用户独立权限。"""
        return self._data.assign_user_permissions(
            user_id=user_id,
            permission_ids=permission_ids,
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
        nickname: str | None = None,
        email: str | None = None,
        phone: str | None = None,
        password: str | None = None,
    ) -> dict:
        """更新当前用户资料；主动改密时清除强制改密标志。"""
        return self._data.update_profile(
            user_id=user_id,
            nickname=nickname,
            email=email,
            phone=phone,
            password_hash=hash_password(password) if password else None,
        )

    def reset_user_password(
        self,
        *,
        user_id: int,
        new_password: str,
    ) -> dict:
        """管理员无复杂度限制重置密码。"""
        return self._data.reset_user_password(
            user_id=user_id,
            password_hash=hash_password(new_password),
        )

    def update_vip(
        self,
        *,
        user_id: int,
        is_vip: bool,
        vip_level: int | None,
        vip_expires_at: datetime | None,
    ) -> dict:
        """更新业务 VIP 设置。"""
        return self._data.update_user_vip(
            user_id=user_id,
            is_vip=is_vip,
            vip_level=vip_level,
            vip_expires_at=vip_expires_at,
        )

    def update_status(self, *, user_id: int, status: int) -> dict:
        """启用或停用用户。"""
        return self._data.update_user_status(
            user_id=user_id,
            status=status,
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
