"""backend-data 内部认证数据服务。

本模块负责用户凭据、登录审计、RBAC 上下文以及 Redis 会话的实际读写；
密码哈希与校验仍由 backend-auth 完成。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import TypedDict

from api_common import (
    DuplicateResourceError,
    RateLimitExceededError,
    SessionReplacedError,
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
from sqlalchemy import or_, select, update
from sqlalchemy.exc import SQLAlchemyError
from sqlalchemy.orm import Session

from app.core.redis_client import RateLimitCounterEntry
from app.models.menu import Menu
from app.models.permission import Permission
from app.models.role import Role, UserRole
from app.models.user import User
from app.models.user_permission import UserMenu, UserPermission
from app.services.identity_access_sync_service import IdentityAccessSyncService
from app.services.identity_invite_code_service import InviteCodeService
from app.services.identity_session_service import IdentitySessionService


class RateLimitConsumeItem(TypedDict):
    """认证限流桶消费参数。"""

    bucket: str
    identifier_hash: str
    limit: int
    window_seconds: int


class RateLimitResetItem(TypedDict):
    """认证限流桶重置参数。"""

    bucket: str
    identifier_hash: str


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
        IdentityAccessSyncService(self._session).sync_from_roles(user)

        invite_codes = InviteCodeService()
        invite_codes.consume(invite_code)
        try:
            self._session.commit()
        except SQLAlchemyError:
            self._session.rollback()
            try:
                invite_codes.restore(invite_code)
            except RuntimeError:
                pass
            raise
        token_meta = self._sessions.issue_token_pair(
            user_id=user.id,
            access_token=access_token,
            refresh_token=refresh_token,
        )
        return token_meta

    def get_credentials(self, username: str) -> dict | None:
        """返回可信服务内部使用的密码哈希与账号状态。"""
        credentials = self._session.execute(
            select(
                User.id,
                User.username,
                User.password_hash,
                User.status,
            ).where(
                User.username == username,
                User.deleted_at.is_(None),
            )
        ).one_or_none()
        if credentials is None:
            return None
        return {
            "id": credentials.id,
            "username": credentials.username,
            "password_hash": credentials.password_hash,
            "status": credentials.status,
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
        values: dict[str, object] = {"last_login_at": datetime.now(UTC)}
        if client_ip:
            values["last_login_ip"] = client_ip
        updated_user = self._session.execute(
            update(User)
            .where(
                User.id == user_id,
                User.deleted_at.is_(None),
            )
            .values(**values)
            .returning(User.id, User.status)
        ).one_or_none()
        if updated_user is None:
            self._session.rollback()
            raise TokenInvalidError(message="用户不存在或已删除")
        if updated_user.status != 1:
            self._session.rollback()
            raise UserDisabledError(message="用户已被禁用")
        self._session.commit()
        return self._sessions.replace_token_pair(
            user_id=updated_user.id,
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

    def consume_rate_limit(
        self,
        *,
        bucket: str,
        identifier_hash: str,
        limit: int,
        window_seconds: int,
    ) -> dict[str, int]:
        """在 backend-data 的 Redis 中消费认证限流计数。"""
        rate_limit_key = f"auth:rate-limit:{bucket}:{identifier_hash}"
        count, retry_after_seconds = self._sessions.increment_rate_limit_with_ttl(
            key=rate_limit_key,
            window_seconds=window_seconds,
        )
        if count > limit:
            raise RateLimitExceededError(
                message=f"请求过于频繁，请在 {retry_after_seconds} 秒后重试",
                detail={
                    "retry_after_seconds": retry_after_seconds,
                    "limit": limit,
                    "window_seconds": window_seconds,
                },
            )
        return {
            "count": count,
            "limit": limit,
            "window_seconds": window_seconds,
            "retry_after_seconds": retry_after_seconds,
        }

    def consume_rate_limits(
        self,
        items: list[RateLimitConsumeItem],
    ) -> list[dict[str, int]]:
        """在一次内部 HTTP 与 Redis 事务中消费多个限流桶。"""
        normalized_items = [
            {
                "key": (
                    "auth:rate-limit:" f"{item['bucket']}:{item['identifier_hash']}"
                ),
                "limit": int(item["limit"]),
                "window_seconds": int(item["window_seconds"]),
            }
            for item in items
        ]
        results = self._sessions.increment_rate_limits_with_ttl(
            [
                RateLimitCounterEntry(
                    key=str(item["key"]),
                    window_seconds=int(item["window_seconds"]),
                    limit=int(item["limit"]),
                )
                for item in normalized_items
            ]
        )
        responses: list[dict[str, int]] = []
        for item, result in zip(
            normalized_items,
            results,
        ):
            limit = int(item["limit"])
            window_seconds = int(item["window_seconds"])
            if result.count > limit:
                raise RateLimitExceededError(
                    message=(
                        "请求过于频繁，请在 " f"{result.retry_after_seconds} 秒后重试"
                    ),
                    detail={
                        "retry_after_seconds": result.retry_after_seconds,
                        "limit": limit,
                        "window_seconds": window_seconds,
                    },
                )
            responses.append(
                {
                    "count": result.count,
                    "limit": limit,
                    "window_seconds": window_seconds,
                    "retry_after_seconds": result.retry_after_seconds,
                }
            )
        return responses

    def reset_rate_limit(
        self,
        *,
        bucket: str,
        identifier_hash: str,
    ) -> None:
        """成功登录后清除账号维度限流桶。"""
        self._sessions.reset_rate_limit(f"auth:rate-limit:{bucket}:{identifier_hash}")

    def reset_rate_limits(self, items: list[RateLimitResetItem]) -> None:
        """在一次 Redis 调用中清除多个限流桶。"""
        self._sessions.reset_rate_limits(
            [
                f"auth:rate-limit:{item['bucket']}:{item['identifier_hash']}"
                for item in items
            ]
        )

    def get_current_user_context(
        self,
        access_token: str,
        *,
        include_menus: bool = True,
    ) -> dict:
        """根据 access token 返回用户、角色、权限与可见菜单。"""
        user_id = self._sessions.read_access_token(access_token)
        if user_id is None:
            if self._sessions.was_access_session_replaced(access_token):
                raise SessionReplacedError(
                    message="账号已在其他设备登录，当前会话已失效"
                )
            raise TokenInvalidError(message="access_token 无效或已过期")
        user = self._session.execute(
            select(
                User.id,
                User.username,
                User.nickname,
                User.email,
                User.phone,
                User.avatar_url,
                User.is_vip,
                User.vip_level,
                User.vip_expires_at,
                User.status,
            ).where(
                User.id == user_id,
                User.deleted_at.is_(None),
            )
        ).one_or_none()
        if user is None:
            raise TokenInvalidError(message="用户不存在或已删除")
        if user.status != 1:
            raise UserDisabledError(message="用户已被禁用")

        role_codes = list(
            self._session.scalars(
                select(Role.code)
                .join(UserRole, UserRole.role_id == Role.id)
                .where(
                    UserRole.user_id == user_id,
                    Role.deleted_at.is_(None),
                )
                .order_by(Role.id)
            )
        )
        permission_codes = sorted(
            self._session.scalars(
                select(Permission.code)
                .join(
                    UserPermission,
                    UserPermission.permission_id == Permission.id,
                )
                .where(UserPermission.user_id == user_id)
            )
        )
        menu_set = (
            self._load_effective_menus(
                user_id=user_id,
                role_codes=role_codes,
                permission_codes=permission_codes,
            )
            if include_menus
            else {}
        )
        must_change_password = self._sessions.is_password_change_required(user.id)
        if must_change_password:
            permission_codes = []
            if include_menus:
                menu_set = self._password_change_menu_subset(menu_set)
        effective_is_vip, effective_vip_level = self._effective_vip_values(
            is_vip=user.is_vip,
            vip_level=user.vip_level,
            vip_expires_at=user.vip_expires_at,
        )
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
            "menus": list(menu_set.values()),
            "must_change_password": must_change_password,
        }

    def _load_effective_menus(
        self,
        *,
        user_id: int,
        role_codes: list[str],
        permission_codes: list[str],
    ) -> dict[int, dict[str, int | str | bool | None]]:
        """按用户运行时快照筛选可见菜单。"""
        statement = select(
            Menu.id,
            Menu.parent_id,
            Menu.menu_type,
            Menu.title,
            Menu.path,
            Menu.component,
            Menu.icon,
            Menu.permission,
            Menu.sort,
            Menu.visible,
        ).where(
            Menu.deleted_at.is_(None),
            Menu.menu_type != MenuType.ACTION,
            Menu.visible.is_(True),
        )
        if FULL_ACCESS_ROLE_CODES.intersection(role_codes):
            menu_rows = self._session.execute(
                statement.order_by(Menu.sort, Menu.id)
            ).mappings()
        else:
            statement = (
                statement.join(UserMenu, UserMenu.menu_id == Menu.id)
                .where(
                    UserMenu.user_id == user_id,
                    or_(
                        Menu.permission.is_(None),
                        Menu.permission.in_(permission_codes),
                    ),
                )
                .order_by(Menu.sort, Menu.id)
            )
            menu_rows = self._session.execute(statement).mappings()
        return {
            int(menu["id"]): {
                "id": int(menu["id"]),
                "parent_id": int(menu["parent_id"]),
                "menu_type": int(menu["menu_type"]),
                "title": str(menu["title"]),
                "path": str(menu["path"]) if menu["path"] is not None else None,
                "component": (
                    str(menu["component"]) if menu["component"] is not None else None
                ),
                "icon": str(menu["icon"]) if menu["icon"] is not None else None,
                "permission": (
                    str(menu["permission"]) if menu["permission"] is not None else None
                ),
                "sort": int(menu["sort"]),
                "visible": bool(menu["visible"]),
            }
            for menu in menu_rows
        }

    @staticmethod
    def _password_change_menu_subset(
        menus: dict[int, dict[str, int | str | bool | None]],
    ) -> dict[int, dict[str, int | str | bool | None]]:
        """强制改密期间只保留个人信息页及其父目录。"""
        profile_menu = next(
            (
                menu
                for menu in menus.values()
                if menu["path"] == USER_PROFILE_ROUTE_PATH
            ),
            None,
        )
        if profile_menu is None:
            return {}
        allowed_ids = {int(profile_menu["id"])}
        parent_id = int(profile_menu["parent_id"])
        while parent_id and parent_id not in allowed_ids:
            parent = menus.get(parent_id)
            if parent is None:
                break
            allowed_ids.add(int(parent["id"]))
            parent_id = int(parent["parent_id"])
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

    @staticmethod
    def _effective_vip_values(
        *,
        is_vip: bool,
        vip_level: int,
        vip_expires_at: datetime | None,
    ) -> tuple[bool, int]:
        """按过期时间计算登录上下文中的有效 VIP。"""
        level = int(vip_level or VipLevel.NORMAL)
        if level in {VipLevel.MANAGER, VipLevel.SUPER_ADMIN}:
            return True, level
        if not is_vip or vip_expires_at is None:
            return False, int(VipLevel.NORMAL)
        expires_at = vip_expires_at
        if expires_at.tzinfo is None:
            expires_at = expires_at.replace(tzinfo=UTC)
        if expires_at <= datetime.now(UTC):
            return False, int(VipLevel.NORMAL)
        return True, level
