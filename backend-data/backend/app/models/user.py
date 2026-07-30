"""用户账号表 ORM 模型。

对应 docs/schema.sql 中的 users 表，承载用户基本信息、VIP 标记与登录状态。
软删除通过 deleted_at 实现，查询时需带 WHERE deleted_at IS NULL。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, Boolean, SmallInteger, String
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.core.database import Base

if TYPE_CHECKING:
    from app.models.menu import Menu
    from app.models.permission import Permission
    from app.models.role import Role


class User(Base):
    """用户账号表。"""

    __tablename__ = "users"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    username: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    password_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    email: Mapped[str | None] = mapped_column(String(128), unique=True)
    phone: Mapped[str | None] = mapped_column(String(32))
    nickname: Mapped[str | None] = mapped_column(String(64))
    avatar_url: Mapped[str | None] = mapped_column(String(512))
    status: Mapped[int] = mapped_column(SmallInteger, default=1, nullable=False)
    is_vip: Mapped[bool] = mapped_column(Boolean, default=False, nullable=False)
    vip_expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    vip_level: Mapped[int] = mapped_column(
        SmallInteger,
        default=0,
        nullable=False,
    )
    last_login_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    last_login_ip: Mapped[str | None] = mapped_column(String(64))
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
        secondary="user_roles",
        back_populates="users",
        lazy="selectin",
    )
    # 用户运行时权限/菜单快照（由角色模板同步，也可直接调整）
    permissions: Mapped[list[Permission]] = relationship(
        "Permission",
        secondary="user_permissions",
        lazy="selectin",
    )
    menus: Mapped[list[Menu]] = relationship(
        "Menu",
        secondary="user_menus",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<User id={self.id} username={self.username!r}>"
