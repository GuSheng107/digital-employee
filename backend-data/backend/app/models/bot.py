"""Bot 定义、Bot 调用授权与用户-Bot 关联 ORM 模型。

对应 docs/schema.sql 中的 bots、bot_call_permissions、user_bots 表。
Bot 通过 parent_bot_id 构成树形（类似部门关系），跨部门补充授权走
bot_call_permissions。app_secret 以 ``enc:v1:`` 前缀的可逆加密形式存库
（详见 backend-share/crypto 包），仅在 service 层读出时解密为明文供 Gateway 使用。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, Integer, SmallInteger, String, Text, text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class Bot(Base):
    """Bot 定义表。

    - ``bot_id``：业务唯一标识，gateway 用。唯一性以 partial unique index
      约束（仅 deleted_at IS NULL 的行唯一），软删除后允许同 bot_id 重建。
    - ``parent_bot_id``：树形结构表达部门隶属
    - ``app_secret``：平台应用密钥（``enc:v1:`` 前缀加密存储）
    - ``mode``：test / prod
    """

    __tablename__ = "bots"
    __table_args__ = (
        # 软删除行不参与唯一性约束，删除后允许同 bot_id 重建。
        # postgresql_where / sqlite_where 在各自方言下生成 partial unique index；
        # 另一方言下对应参数被忽略，互不干扰。
        Index(
            "uq_bots_bot_id_active",
            "bot_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(
        BigInteger().with_variant(Integer, "sqlite"), primary_key=True
    )
    bot_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    platform: Mapped[str] = mapped_column(String(32), nullable=False)
    app_id: Mapped[str | None] = mapped_column(String(128))
    app_secret: Mapped[str | None] = mapped_column(Text)
    parent_bot_id: Mapped[int | None] = mapped_column(
        ForeignKey("bots.id", ondelete="SET NULL")
    )
    mode: Mapped[str] = mapped_column(String(16), default="test")
    status: Mapped[int] = mapped_column(SmallInteger, default=1)
    created_by: Mapped[int | None] = mapped_column(BigInteger)
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

    def __repr__(self) -> str:
        return f"<Bot id={self.id} bot_id={self.bot_id!r}>"


class BotCallPermission(Base):
    """Bot 额外调用授权（树形外补充）。

    - ``caller_bot_id``：调用方
    - ``target_bot_id``：被调用方
    - ``permission``：如 ``call_agent`` / ``route_message``
    - ``expires_at``：NULL 表示永久
    """

    __tablename__ = "bot_call_permissions"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    caller_bot_id: Mapped[int] = mapped_column(
        ForeignKey("bots.id", ondelete="CASCADE"), nullable=False
    )
    target_bot_id: Mapped[int] = mapped_column(
        ForeignKey("bots.id", ondelete="CASCADE"), nullable=False
    )
    permission: Mapped[str] = mapped_column(String(64), nullable=False)
    granted_by: Mapped[int | None] = mapped_column(BigInteger)
    expires_at: Mapped[datetime | None] = mapped_column(TIMESTAMP(timezone=True))
    created_at: Mapped[datetime] = mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:
        return (
            f"<BotCallPermission caller={self.caller_bot_id} "
            f"target={self.target_bot_id} perm={self.permission!r}>"
        )


class UserBot(Base):
    """用户-Bot 关联表（多对多）。"""

    __tablename__ = "user_bots"

    user_id: Mapped[int] = mapped_column(
        ForeignKey("users.id", ondelete="CASCADE"),
        primary_key=True,
    )
    bot_id: Mapped[int] = mapped_column(
        ForeignKey("bots.id", ondelete="CASCADE"),
        primary_key=True,
    )
