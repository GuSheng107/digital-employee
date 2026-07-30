"""把角色模板权限同步为用户运行时权限快照。"""

from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.menu import Menu
from app.models.permission import Permission
from app.models.user import User


@dataclass(frozen=True)
class UserAccessExtras:
    """用户在角色模板之外单独获得的权限与菜单。"""

    menu_ids: frozenset[int]
    permission_ids: frozenset[int]


class IdentityAccessSyncService:
    """维护角色模板与用户运行时权限快照的一致性。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    @staticmethod
    def capture_extras(user: User) -> UserAccessExtras:
        """在角色变更前提取用户的独立授权。"""
        role_menu_ids = {
            menu.id
            for role in user.roles
            for menu in role.menus
            if menu.deleted_at is None
        }
        role_permission_ids = {
            permission.id
            for role in user.roles
            for permission in role.permissions
        }
        return UserAccessExtras(
            menu_ids=frozenset(
                menu.id
                for menu in user.menus
                if menu.deleted_at is None and menu.id not in role_menu_ids
            ),
            permission_ids=frozenset(
                permission.id
                for permission in user.permissions
                if permission.id not in role_permission_ids
            ),
        )

    def sync_from_roles(
        self,
        user: User,
        *,
        extras: UserAccessExtras | None = None,
    ) -> None:
        """把用户多个角色的权限并集写入用户权限快照。"""
        preserved = extras or UserAccessExtras(
            menu_ids=frozenset(),
            permission_ids=frozenset(),
        )
        menu_ids = set(preserved.menu_ids)
        permission_ids = set(preserved.permission_ids)
        for role in user.roles:
            menu_ids.update(
                menu.id for menu in role.menus if menu.deleted_at is None
            )
            permission_ids.update(
                permission.id for permission in role.permissions
            )

        user.menus = (
            list(
                self._session.scalars(
                    select(Menu).where(
                        Menu.id.in_(menu_ids),
                        Menu.deleted_at.is_(None),
                    )
                ).all()
            )
            if menu_ids
            else []
        )
        user.permissions = (
            list(
                self._session.scalars(
                    select(Permission).where(Permission.id.in_(permission_ids))
                ).all()
            )
            if permission_ids
            else []
        )
