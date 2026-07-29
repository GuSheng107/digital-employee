"""backend-data 内部认证数据服务。

本模块负责用户凭据、登录审计、RBAC 上下文以及 Redis 会话的实际读写；
密码哈希与校验仍由 backend-auth 完成。
"""

from __future__ import annotations

from datetime import UTC, datetime

from api_common import (
    DuplicateResourceError,
    ServiceUnavailableError,
    TokenInvalidError,
    UserDisabledError,
)
from auth_utils import (
    FULL_ACCESS_ROLE_CODES,
    ROLE_CODE_USER,
    USER_PROFILE_ROUTE_PATH,
    MenuType,
    VipLevel,
    get_vip_display,
)
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.menu import Menu
from app.models.role import Role
from app.models.user import User
from app.services.identity_invite_code_service import InviteCodeService
from app.services.identity_session_service import IdentitySessionService


class IdentityAuthService:
    """认证域所需的 PostgreSQL 与 Redis 数据操作。"""

    def __init__(self, session: Session) -> None:
        self._session = session
        self._sessions = IdentitySessionService()

    def register(
        self,
        *,
        username: str,
        password_hash: str,
        email: str,
        phone: str,
        invite_code: str,
        access_token: str,
        refresh_token: str,
    ) -> dict:
        """创建普通用户、消费邀请码并写入初始会话。"""
        if self._fetch_user_by_username(username) is not None:
            raise DuplicateResourceError(message="用户名已存在")
        if self._fetch_user_by_email(email) is not None:
            raise DuplicateResourceError(message="邮箱已被使用")
        user_role = self._session.scalars(
            select(Role).where(
                Role.code == ROLE_CODE_USER,
                Role.deleted_at.is_(None),
            )
        ).first()
        if user_role is None:
            raise ServiceUnavailableError(message="系统默认用户角色尚未配置")

        user = User(
            username=username,
            password_hash=password_hash,
            email=email,
            phone=phone,
            status=1,
            is_vip=False,
            vip_level=VipLevel.NORMAL,
        )
        self._session.add(user)
        self._session.flush()
        user.roles.append(user_role)

        InviteCodeService().consume(invite_code)
        self._session.commit()
        token_meta = self._sessions.issue_token_pair(
            user_id=user.id,
            access_token=access_token,
            refresh_token=refresh_token,
        )
        return token_meta

    def get_credentials(self, username: str) -> dict | None:
        """返回可信服务内部使用的密码哈希与账号状态。"""
        user = self._fetch_user_by_username(username)
        if user is None:
            return None
        return {
            "id": user.id,
            "username": user.username,
            "password_hash": user.password_hash,
            "status": user.status,
        }

    def complete_login(
        self,
        *,
        user_id: int,
        client_ip: str | None,
        access_token: str,
        refresh_token: str,
    ) -> dict:
        """更新登录审计、撤销旧会话并写入新会话。"""
        user = self._get_active_user(user_id)
        user.last_login_at = datetime.now(UTC)
        if client_ip:
            user.last_login_ip = client_ip
        self._session.commit()
        return self._sessions.replace_token_pair(
            user_id=user.id,
            access_token=access_token,
            refresh_token=refresh_token,
        )

    def refresh_session(
        self,
        *,
        refresh_token: str,
        new_access_token: str,
        new_refresh_token: str,
    ) -> dict:
        """校验 refresh token 与用户状态并完成一次性轮换。"""
        user_id = self._sessions.read_refresh_token(refresh_token)
        if user_id is None:
            raise TokenInvalidError(message="refresh_token 无效或已过期")
        self._get_active_user(user_id)
        return self._sessions.rotate_token_pair(
            old_refresh_token=refresh_token,
            user_id=user_id,
            new_access_token=new_access_token,
            new_refresh_token=new_refresh_token,
        )

    def logout(
        self,
        *,
        access_token: str,
        refresh_token: str | None,
    ) -> None:
        """撤销当前会话。"""
        self._sessions.logout(
            access_token=access_token,
            refresh_token=refresh_token,
        )

    def get_current_user_context(self, access_token: str) -> dict:
        """根据 access token 返回用户、角色、权限与可见菜单。"""
        user_id = self._sessions.read_access_token(access_token)
        if user_id is None:
            raise TokenInvalidError(message="access_token 无效或已过期")
        user = self._get_active_user(user_id)
        role_codes = [role.code for role in user.roles]
        permission_codes = sorted(
            {permission.code for role in user.roles for permission in role.permissions}
            | {permission.code for permission in user.permissions}
        )
        menu_set = self._load_effective_menus(
            user=user,
            role_codes=role_codes,
            permission_codes=permission_codes,
        )
        must_change_password = self._sessions.is_password_change_required(user.id)
        if must_change_password:
            permission_codes = []
            menu_set = self._password_change_menu_subset(menu_set)
        effective_is_vip, effective_vip_level = self._effective_vip(user)
        return {
            "id": user.id,
            "username": user.username,
            "nickname": user.nickname,
            "email": user.email,
            "phone": user.phone,
            "avatar_url": user.avatar_url,
            "is_vip": effective_is_vip,
            "vip_level": effective_vip_level,
            "vip_level_display": get_vip_display(effective_vip_level),
            "vip_expires_at": user.vip_expires_at.isoformat()
            if user.vip_expires_at
            else None,
            "status": user.status,
            "roles": role_codes,
            "permissions": permission_codes,
            "menus": [self._menu_to_dict(menu) for menu in menu_set.values()],
            "must_change_password": must_change_password,
        }

    def _load_effective_menus(
        self,
        *,
        user: User,
        role_codes: list[str],
        permission_codes: list[str],
    ) -> dict[int, Menu]:
        """计算角色菜单与用户独立菜单的有效并集。"""
        if FULL_ACCESS_ROLE_CODES.intersection(role_codes):
            menus = self._session.scalars(
                select(Menu).where(
                    Menu.deleted_at.is_(None),
                    Menu.menu_type != MenuType.ACTION,
                    Menu.visible.is_(True),
                )
            ).all()
            return {menu.id: menu for menu in menus}

        effective_permissions = set(permission_codes)
        candidates = {menu.id: menu for role in user.roles for menu in role.menus}
        candidates.update({menu.id: menu for menu in user.menus})
        result: dict[int, Menu] = {}
        for menu in candidates.values():
            has_permission = (
                menu.permission is None or menu.permission in effective_permissions
            )
            if (
                menu.deleted_at is None
                and menu.menu_type != MenuType.ACTION
                and menu.visible
                and has_permission
            ):
                result[menu.id] = menu
        return result

    @staticmethod
    def _password_change_menu_subset(
        menus: dict[int, Menu],
    ) -> dict[int, Menu]:
        """强制改密期间只保留个人信息页及其父目录。"""
        profile_menu = next(
            (menu for menu in menus.values() if menu.path == USER_PROFILE_ROUTE_PATH),
            None,
        )
        if profile_menu is None:
            return {}
        allowed_ids = {profile_menu.id}
        parent_id = profile_menu.parent_id
        while parent_id and parent_id not in allowed_ids:
            parent = menus.get(parent_id)
            if parent is None:
                break
            allowed_ids.add(parent.id)
            parent_id = parent.parent_id
        return {
            menu_id: menu for menu_id, menu in menus.items() if menu_id in allowed_ids
        }

    def _get_active_user(self, user_id: int) -> User:
        user = self._session.get(User, user_id)
        if user is None or user.deleted_at is not None:
            raise TokenInvalidError(message="用户不存在或已删除")
        if user.status != 1:
            raise UserDisabledError(message="用户已被禁用")
        return user

    def _fetch_user_by_username(self, username: str) -> User | None:
        return self._session.execute(
            select(User).where(
                User.username == username,
                User.deleted_at.is_(None),
            )
        ).scalar_one_or_none()

    def _fetch_user_by_email(self, email: str) -> User | None:
        return self._session.execute(
            select(User).where(
                User.email == email,
                User.deleted_at.is_(None),
            )
        ).scalar_one_or_none()

    def _effective_vip(self, user: User) -> tuple[bool, int]:
        """按过期时间计算登录上下文中的有效 VIP。"""
        level = int(user.vip_level or VipLevel.NORMAL)
        if level in {VipLevel.MANAGER, VipLevel.SUPER_ADMIN}:
            return True, level
        if not user.is_vip or user.vip_expires_at is None:
            return False, int(VipLevel.NORMAL)
        expires_at = user.vip_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            return False, int(VipLevel.NORMAL)
        return True, level

    @staticmethod
    def _menu_to_dict(menu: Menu) -> dict:
        return {
            "id": menu.id,
            "parent_id": menu.parent_id,
            "menu_type": menu.menu_type,
            "title": menu.title,
            "path": menu.path,
            "component": menu.component,
            "icon": menu.icon,
            "permission": menu.permission,
            "sort": menu.sort,
            "visible": menu.visible,
        }
