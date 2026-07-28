"""Agent 定义与 Bot→Agent 可见性映射 ORM 模型。

对应 docs/schema.sql 中的 agents 和 bot_agents 表。Agent 表示可被 Bot
调用的下游智能体服务，通过 bot_agents 控制每个 Bot 可见的 Agent 集合。
"""

from __future__ import annotations

from datetime import datetime
from typing import TYPE_CHECKING

from sqlalchemy import BigInteger, ForeignKey, SmallInteger, String
from sqlalchemy.dialects.postgresql import TIMESTAMP
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.sql import func

from app.models.base import Base

if TYPE_CHECKING:
    from app.models.bot import Bot


class Agent(Base):
    """Agent 定义表。

    - ``agent_id``：业务唯一标识
    - ``endpoint``：agent 服务地址，供 gateway 路由调用
    - ``status``：1=启用 0=禁用
    """

    __tablename__ = "agents"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True)
    agent_id: Mapped[str] = mapped_column(String(64), unique=True, nullable=False)
    name: Mapped[str] = mapped_column(String(128), nullable=False)
    description: Mapped[str] = mapped_column(String(255), default="")
    endpoint: Mapped[str | None] = mapped_column(String(255))
    status: Mapped[int] = mapped_column(SmallInteger, default=1)
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

    bots: Mapped[list[Bot]] = relationship(
        "Bot",
        secondary="bot_agents",
        back_populates="agents",
        lazy="selectin",
    )

    def __repr__(self) -> str:
        return f"<Agent id={self.id} agent_id={self.agent_id!r}>"


class BotAgent(Base):
    """Bot→Agent 可见性映射表（多对多）。"""

    __tablename__ = "bot_agents"

    bot_id: Mapped[int] = mapped_column(
        ForeignKey("bots.id", ondelete="CASCADE"),
        primary_key=True,
    )
    agent_id: Mapped[int] = mapped_column(
        ForeignKey("agents.id", ondelete="CASCADE"),
        primary_key=True,
    )
