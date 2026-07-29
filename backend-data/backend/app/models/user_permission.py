"""用户独立权限/菜单关联表 ORM 模型。

权限组（Role）作为基础授权；分配角色时会把当时的权限点和菜单同步到
用户独立集合（user_permissions / user_menus），之后仍可单独调整。

最终授权由当前角色授权与用户直接授权取并集。
"""

from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserPermission(Base):
    """用户-权限关联表（多对多，独立于角色）。

    用户最终权限 = 当前角色权限与 user_permissions 直接权限的并集。
    """

    __tablename__ = "user_permissions"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    permission_id: Mapped[int] = mapped_column(
        ForeignKey("permissions.id", ondelete="CASCADE"),
        primary_key=True,
    )


class UserMenu(Base):
    """用户-菜单关联表（多对多，独立于角色）。

    用户最终菜单 = 当前角色菜单与 user_menus 直接菜单的并集。
    """

    __tablename__ = "user_menus"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    menu_id: Mapped[int] = mapped_column(
        ForeignKey("menus.id", ondelete="CASCADE"),
        primary_key=True,
    )
