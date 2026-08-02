"""Agent 定义 ORM 模型。

对应 docs/schema.sql 中的 agents 表。
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import BigInteger, ForeignKey, Index, SmallInteger, String, text
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func

from app.core.database import Base


class Agent(Base):
    """Agent 定义表。

    - ``agent_id``：业务唯一标识
    - ``status``：1=启用 0=禁用
    - ``created_by``：创建者用户 ID
    """

    __tablename__ = "agents"
    __table_args__ = (
        Index(
            "uq_agents_agent_id_active",
            "agent_id",
            unique=True,
            postgresql_where=text("deleted_at IS NULL"),
            sqlite_where=text("deleted_at IS NULL"),
        ),
    )

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(64), nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    status: Mapped[int] = mapped_column(SmallInteger, default=1)
    created_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("users.id", ondelete="SET NULL")
    )
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
        return f"<Agent id={self.id} agent_id={self.agent_id!r}>"
