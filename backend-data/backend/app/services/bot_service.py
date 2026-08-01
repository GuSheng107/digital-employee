"""Bot 管理业务逻辑层。

负责 Bot 的 CRUD 操作，包括分页查询、创建、更新、软删除。

app_secret 加密策略：
- 写入（create/update）：调用 ``secret_crypto.encrypt`` 加密后落库，密文带
  ``enc:v1:`` 前缀。
- 读取给 Gateway（``list_active_bots``）：调 ``secret_crypto.decrypt`` 还原明文，
  Gateway 拿到的是明文，零改动。
- 读取给前端（``list_bots``）：app_secret 脱敏为 ``***``，不暴露密文也不暴露明文。
- 兼容过渡：``decrypt`` 见到无前缀的值视为明文原样返回，存量数据迁移前可正常工作。
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from api_common import DuplicateResourceError, ResourceNotFoundError
from secret_crypto import decrypt, encrypt

from app.core.database import DatabaseRole, get_database_client
from app.models.agent import Agent
from app.models.bot import Bot
from app.models.user import User
from sqlalchemy import func


def _bot_to_dict(
    bot: Bot,
    *,
    mask_secret: bool = False,
    created_by_name: str | None = None,
    agent_name: str | None = None,
) -> dict[str, Any]:
    """将 Bot ORM 对象转换为字典。

    Args:
        bot: Bot ORM 实例。
        mask_secret: 是否脱敏 app_secret。脱敏时返回 ``***``；不脱敏时返回
            解密后的明文（供 Gateway 使用）。
        created_by_name: 创建者的显示名称/用户名（联查时提供）。
        agent_name: 关联 Agent 的名称（联查时提供）。
    """
    return {
        "id": bot.id,
        "bot_id": bot.bot_id,
        "name": bot.name,
        "platform": bot.platform,
        "app_id": bot.app_id,
        "app_secret": "***" if mask_secret else decrypt(bot.app_secret or ""),
        "mode": bot.mode,
        "status": bot.status,
        "agent_id": bot.agent_id,
        "agent_name": agent_name,
        "created_by": bot.created_by,
        "created_by_name": created_by_name,
        "created_at": bot.created_at.isoformat() if bot.created_at else None,
        "updated_at": bot.updated_at.isoformat() if bot.updated_at else None,
    }


class BotService:
    """Bot 管理服务。"""

    def __init__(self) -> None:
        self._db = get_database_client(DatabaseRole.CORE)

    def list_bots(
        self,
        *,
        page: int,
        page_size: int,
        created_by: int | None = None,
    ) -> dict[str, Any]:
        """分页查询未删除的 Bot 列表（前端管理页用，app_secret 脱敏，联查创建者）。"""
        offset = (page - 1) * page_size
        with self._db.session() as session:
            query = (
                session.query(
                    Bot,
                    func.coalesce(User.nickname, User.username).label("creator_name"),
                    func.coalesce(Agent.name, Bot.agent_id).label("agent_name"),
                )
                .outerjoin(User, Bot.created_by == User.id)
                .outerjoin(Agent, Bot.agent_id == Agent.agent_id)
                .filter(Bot.deleted_at.is_(None))
            )
            if created_by is not None:
                query = query.filter(Bot.created_by == created_by)
            total = query.count()
            rows = (
                query.order_by(Bot.id.desc())
                .offset(offset)
                .limit(page_size)
                .all()
            )
            items = [
                _bot_to_dict(
                    bot,
                    mask_secret=True,
                    created_by_name=creator_name,
                    agent_name=agent_name,
                )
                for bot, creator_name, agent_name in rows
            ]
            return {
                "items": items,
                "total": total,
                "page": page,
                "page_size": page_size,
            }

    def get_bot(self, *, bot_id: str) -> dict[str, Any]:
        """获取单个 Bot 详情。"""
        with self._db.session() as session:
            row = (
                session.query(
                    Bot,
                    func.coalesce(User.nickname, User.username).label("creator_name"),
                    func.coalesce(Agent.name, Bot.agent_id).label("agent_name"),
                )
                .outerjoin(User, Bot.created_by == User.id)
                .outerjoin(Agent, Bot.agent_id == Agent.agent_id)
                .filter(Bot.bot_id == bot_id, Bot.deleted_at.is_(None))
                .first()
            )
            if row is None:
                raise ResourceNotFoundError(message=f"Bot '{bot_id}' 不存在")
            bot, creator_name, agent_name = row
            return _bot_to_dict(
                bot,
                mask_secret=True,
                created_by_name=creator_name,
                agent_name=agent_name,
            )

    def list_active_bots(self) -> list[dict[str, Any]]:
        """查询全部启用的 Bot（Gateway 启动拉取用，含 app_secret 明文）。"""
        with self._db.session() as session:
            bots = (
                session.query(Bot)
                .filter(Bot.deleted_at.is_(None), Bot.status == 1)
                .all()
            )
            return [_bot_to_dict(b, mask_secret=False) for b in bots]

    def create_bot(
        self,
        *,
        bot_id: str,
        name: str,
        platform: str,
        app_id: str,
        app_secret: str,
        mode: str = "test",
        agent_id: str | None = None,
        created_by: int | None = None,
    ) -> dict[str, Any]:
        """创建 Bot。"""
        with self._db.session() as session:
            existing = (
                session.query(Bot)
                .filter(Bot.bot_id == bot_id, Bot.deleted_at.is_(None))
                .first()
            )
            if existing is not None:
                raise DuplicateResourceError(
                    message=f"Bot '{bot_id}' 已存在",
                )

            bot = Bot(
                bot_id=bot_id,
                name=name,
                platform=platform,
                app_id=app_id,
                app_secret=encrypt(app_secret),
                mode=mode,
                status=1,
                agent_id=agent_id,
                created_by=created_by,
            )
            session.add(bot)
            session.commit()
            session.refresh(bot)
            return _bot_to_dict(bot, mask_secret=True)

    def update_bot(self, *, bot_id: str, **fields: Any) -> dict[str, Any]:
        """更新 Bot 配置（只更新传入的字段）。

        Args:
            bot_id: 目标 Bot 的业务标识。
            **fields: 待更新字段。若包含 ``app_secret``，会先加密再落库。

        Returns:
            更新后的 Bot 字典（app_secret 脱敏）。

        Raises:
            ResourceNotFoundError: Bot 不存在或已删除。
        """
        with self._db.session() as session:
            bot = (
                session.query(Bot)
                .filter(Bot.bot_id == bot_id, Bot.deleted_at.is_(None))
                .first()
            )
            if bot is None:
                raise ResourceNotFoundError(
                    message=f"Bot '{bot_id}' 不存在",
                )
            for key, value in fields.items():
                if value is not None and hasattr(bot, key):
                    setattr(bot, key, encrypt(value) if key == "app_secret" else value)
            session.commit()
            session.refresh(bot)
            return _bot_to_dict(bot, mask_secret=True)

    def delete_bot(self, *, bot_id: str) -> dict[str, Any]:
        """软删除 Bot（填写 deleted_at）。

        软删除后同 ``bot_id`` 可再次创建（partial unique index 仅约束
        ``deleted_at IS NULL`` 的行），实现「删除后重建」语义。

        Args:
            bot_id: 目标 Bot 的业务标识。

        Returns:
            确认删除的响应字典。

        Raises:
            ResourceNotFoundError: Bot 不存在或已删除。
        """
        with self._db.session() as session:
            bot = (
                session.query(Bot)
                .filter(Bot.bot_id == bot_id, Bot.deleted_at.is_(None))
                .first()
            )
            if bot is None:
                raise ResourceNotFoundError(
                    message=f"Bot '{bot_id}' 不存在",
                )
            bot.deleted_at = datetime.now(tz=UTC)
            session.commit()
            return {"bot_id": bot_id, "deleted": True}
