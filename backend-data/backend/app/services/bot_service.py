"""Bot 管理业务逻辑层。

负责 Bot 的 CRUD 操作，包括分页查询、创建、更新、软删除。
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from api_common import DuplicateResourceError, ResourceNotFoundError

from app.core.database import DatabaseRole, get_database_client
from app.models.bot import Bot


def _bot_to_dict(bot: Bot, *, mask_secret: bool = False) -> dict[str, Any]:
    """将 Bot ORM 对象转换为字典。

    Args:
        bot: Bot ORM 实例。
        mask_secret: 是否脱敏 app_secret。
    """
    return {
        "id": bot.id,
        "bot_id": bot.bot_id,
        "name": bot.name,
        "platform": bot.platform,
        "app_id": bot.app_id,
        "app_secret": "***" if mask_secret else bot.app_secret,
        "mode": bot.mode,
        "status": bot.status,
        "created_at": bot.created_at.isoformat() if bot.created_at else None,
        "updated_at": bot.updated_at.isoformat() if bot.updated_at else None,
    }


class BotService:
    """Bot 管理服务。"""

    def __init__(self) -> None:
        self._db = get_database_client(DatabaseRole.CORE)

    def list_bots(self, *, page: int, page_size: int) -> dict[str, Any]:
        """分页查询未删除的 Bot 列表（前端管理页用，app_secret 脱敏）。"""
        offset = (page - 1) * page_size
        with self._db.session() as session:
            query = session.query(Bot).filter(Bot.deleted_at.is_(None))
            total = query.count()
            bots = (
                query.order_by(Bot.id.desc())
                .offset(offset)
                .limit(page_size)
                .all()
            )
            return {
                "items": [_bot_to_dict(b, mask_secret=True) for b in bots],
                "total": total,
                "page": page,
                "page_size": page_size,
            }

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
    ) -> dict[str, Any]:
        """创建 Bot。

        Args:
            bot_id: 业务唯一标识。
            name: Bot 显示名称。
            platform: 平台类型（feishu / wechat）。
            app_id: 平台应用 ID。
            app_secret: 平台应用密钥。
            mode: 运行模式（test / prod）。

        Returns:
            创建后的 Bot 字典（app_secret 脱敏）。

        Raises:
            DuplicateResourceError: bot_id 已存在。
        """
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
                app_secret=app_secret,
                mode=mode,
                status=1,
            )
            session.add(bot)
            session.commit()
            session.refresh(bot)
            return _bot_to_dict(bot, mask_secret=True)

    def update_bot(self, *, bot_id: str, **fields: Any) -> dict[str, Any]:
        """更新 Bot 配置（只更新传入的字段）。

        Args:
            bot_id: 目标 Bot 的业务标识。
            **fields: 待更新字段。

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
                    setattr(bot, key, value)
            session.commit()
            session.refresh(bot)
            return _bot_to_dict(bot, mask_secret=True)

    def delete_bot(self, *, bot_id: str) -> dict[str, Any]:
        """软删除 Bot（填写 deleted_at）。

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
            bot.deleted_at = datetime.now(tz=timezone.utc)
            session.commit()
            return {"bot_id": bot_id, "deleted": True}
