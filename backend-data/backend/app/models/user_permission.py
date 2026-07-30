"""用户运行时权限与菜单快照关联表 ORM 模型。

角色作为授权模板；分配或修改角色时把多个角色的并集同步到
``user_permissions`` 与 ``user_menus``。运行时只读取用户快照，
管理员仍可在自身权限范围内直接调整快照。
"""

from __future__ import annotations

from sqlalchemy import ForeignKey
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class UserPermission(Base):
    """用户运行时权限快照关联表。"""

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
    """用户运行时菜单快照关联表。"""

    __tablename__ = "user_menus"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    menu_id: Mapped[int] = mapped_column(
        ForeignKey("menus.id", ondelete="CASCADE"),
        primary_key=True,
    )
