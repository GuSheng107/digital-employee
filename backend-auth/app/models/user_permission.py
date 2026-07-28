"""用户独立权限/菜单关联表 ORM 模型。

权限组（Role）作为模板：当为用户分配角色时，会把角色的权限点和菜单
复制到用户的独立集合（user_permissions / user_menus）。之后用户可以
独立增删自己的权限/菜单，不受角色变更影响。

这样角色真正成为"权限模板"，而用户持有"权限副本"，可个性化调整。
"""

from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base


class UserPermission(Base):
    """用户-权限关联表（多对多，独立于角色）。

    用户最终的权限 = user_permissions 中持有的权限点（不再通过角色继承）。
    分配角色时会把角色权限复制到本表，用户可再自行增删。
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

    用户最终的菜单 = user_menus 中持有的菜单（不再通过角色继承）。
    分配角色时会把角色菜单复制到本表，用户可再自行增删。
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
