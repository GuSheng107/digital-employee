"""前端菜单表与角色-菜单关联 ORM 模型。

对应 docs/schema.sql 中的 menus 和 role_menus 表。菜单为树形结构，
parent_id=0 表示顶级；menu_type 区分目录/菜单/按钮。permission 字段
绑定权限码，空值表示仅登录可见。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, ForeignKey, Integer, SmallInteger, String
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.role import Role


class Menu(Base):
    """前端菜单表（树形）。

    - ``menu_type``：1=目录 2=菜单 3=按钮
    - ``parent_id``：0 表示顶级
    - ``permission``：所需权限码，空值表示仅登录可见
    """

    __tablename__ = "menus"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    parent_id: Mapped[int] = mapped_column(BigInteger, default=0)
    menu_type: Mapped[int] = mapped_column(SmallInteger, nullable=False)
    title: Mapped[str] = mapped_column(String(64), nullable=False)
    path: Mapped[str | None] = mapped_column(String(255))
    component: Mapped[str | None] = mapped_column(String(255))
    icon: Mapped[str | None] = mapped_column(String(64))
    permission: Mapped[str | None] = mapped_column(String(128))
    sort: Mapped[int] = mapped_column(Integer, default=0)
    visible: Mapped[bool] = mapped_column(Boolean, default=True)
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )
    updated_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True),
        nullable=False,
        server_default=func.now(),
        onupdate=func.now(),
    )
    deleted_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))

    roles: Mapped[list[Role]] = relationship(
        "Role",
        secondary="role_menus",
        back_populates="menus",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Menu id={self.id} title={self.title!r}>"


class RoleMenu(Base):
    """角色-菜单关联表（多对多）。"""

    __tablename__ = "role_menus"

    role_id: Mapped[int] = mapped_column(
        ForeignKey("roles.id", ondelete="CASCADE"),
        primary_key=True,
    )
    menu_id: Mapped[int] = mapped_column(
        ForeignKey("menus.id", ondelete="CASCADE"),
        primary_key=True,
    )
