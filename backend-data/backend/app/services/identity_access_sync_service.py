"""把角色模板权限同步为用户运行时权限快照。"""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.models.menu import Menu
from app.models.permission import Permission
from app.models.user import User


class IdentityAccessSyncService:
    """在角色授权时生成用户运行时权限快照。"""

    def __init__(self, session: Session) -> None:
        self._session = session

    def sync_from_roles(
        self,
        user: User,
    ) -> None:
        """用用户多个角色的权限并集覆盖运行时权限快照。

        角色只在授权动作发生时作为模板使用。授权完成后，运行时鉴权只读取
        用户快照；直接调整的菜单或权限也不会因角色模板后续变化而被改写。
        """
        menu_ids: set[int] = set()
        permission_ids: set[int] = set()
        for role in user.roles:
            menu_ids.update(menu.id for menu in role.menus if menu.deleted_at is None)
            permission_ids.update(permission.id for permission in role.permissions)

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
