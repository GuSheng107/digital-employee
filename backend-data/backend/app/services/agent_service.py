"""Agent 服务逻辑。

提供 Agent 定义的 CRUD 操作，并联查创建者用户名字段。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from api_common import DuplicateResourceError, ResourceNotFoundError
from sqlalchemy import func

from app.core.database import DatabaseRole, get_database_client
from app.models.agent import Agent
from app.models.user import User

# 可空字段白名单：与 bot_service 对称定义。当前 Agent 的可更新字段
# （name / status）均不允许置空，故为空集；保留此结构是为了在未来新增
# 可空字段（如 description、parent_agent_id 等）时无需重构 update 逻辑，
# 只需把字段名加入此集合即可。
NULLABLE_FIELDS: frozenset[str] = frozenset()


def _agent_to_dict(
    agent: Agent,
    *,
    created_by_name: str | None = None,
) -> dict[str, Any]:
    """Agent ORM 对象转字典。"""
    return {
        "id": agent.id,
        "agent_id": agent.agent_id,
        "name": agent.name,
        "status": agent.status,
        "created_by": agent.created_by,
        "created_by_name": created_by_name,
        "created_at": agent.created_at.isoformat() if agent.created_at else None,
        "updated_at": agent.updated_at.isoformat() if agent.updated_at else None,
    }


class AgentService:
    """Agent 管理服务。"""

    def __init__(self) -> None:
        self._db = get_database_client(DatabaseRole.CORE)

    def list_agents(
        self,
        *,
        page: int,
        page_size: int,
        created_by: int | None = None,
    ) -> dict[str, Any]:
        """分页查询未删除的 Agent 列表（联查创建者）。"""
        offset = (page - 1) * page_size
        with self._db.session() as session:
            query = (
                session.query(
                    Agent,
                    func.coalesce(User.nickname, User.username).label("creator_name"),
                )
                .outerjoin(User, Agent.created_by == User.id)
                .filter(Agent.deleted_at.is_(None))
            )
            if created_by is not None:
                query = query.filter(Agent.created_by == created_by)
            total = query.count()
            rows = (
                query.order_by(Agent.id.desc())
                .offset(offset)
                .limit(page_size)
                .all()
            )
            items = [
                _agent_to_dict(agent, created_by_name=creator_name)
                for agent, creator_name in rows
            ]
            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
            }

    def get_agent(self, *, agent_id: str) -> dict[str, Any]:
        """获取单个 Agent 详情。"""
        with self._db.session() as session:
            row = (
                session.query(
                    Agent,
                    func.coalesce(User.nickname, User.username).label("creator_name"),
                )
                .outerjoin(User, Agent.created_by == User.id)
                .filter(Agent.agent_id == agent_id, Agent.deleted_at.is_(None))
                .first()
            )
            if row is None:
                raise ResourceNotFoundError(message=f"Agent '{agent_id}' 不存在")
            agent, creator_name = row
            return _agent_to_dict(agent, created_by_name=creator_name)

    def create_agent(
        self,
        *,
        agent_id: str,
        name: str,
        status: int = 1,
        created_by: int | None = None,
    ) -> dict[str, Any]:
        """创建 Agent。"""
        with self._db.session() as session:
            existing = (
                session.query(Agent)
                .filter(Agent.agent_id == agent_id, Agent.deleted_at.is_(None))
                .first()
            )
            if existing is not None:
                raise DuplicateResourceError(message=f"Agent '{agent_id}' 已存在")

            agent = Agent(
                agent_id=agent_id,
                name=name,
                status=status,
                created_by=created_by,
            )
            session.add(agent)
            session.commit()
            session.refresh(agent)
            return _agent_to_dict(agent)

    def update_agent(self, *, agent_id: str, **fields: Any) -> dict[str, Any]:
        """更新 Agent 配置。"""
        with self._db.session() as session:
            agent = (
                session.query(Agent)
                .filter(Agent.agent_id == agent_id, Agent.deleted_at.is_(None))
                .first()
            )
            if agent is None:
                raise ResourceNotFoundError(message=f"Agent '{agent_id}' 不存在")
            for key, value in fields.items():
                if not hasattr(agent, key):
                    continue
                if value is None and key not in NULLABLE_FIELDS:
                    continue
                setattr(agent, key, value)
            session.commit()
            session.refresh(agent)
            return _agent_to_dict(agent)

    def delete_agent(self, *, agent_id: str) -> dict[str, Any]:
        """软删除 Agent。"""
        with self._db.session() as session:
            agent = (
                session.query(Agent)
                .filter(Agent.agent_id == agent_id, Agent.deleted_at.is_(None))
                .first()
            )
            if agent is None:
                raise ResourceNotFoundError(message=f"Agent '{agent_id}' 不存在")
            agent.deleted_at = datetime.now(tz=UTC)
            session.commit()
            return {"agent_id": agent_id, "deleted": True}
