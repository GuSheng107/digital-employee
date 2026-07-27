from __future__ import annotations

from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.data_item import DataItem
from app.schemas.data_item import DataItemCreate, DataItemUpdate


class DataItemRepository:
    """数据条目仓储层。

    基于 SQLAlchemy Session 提供数据条目的持久化访问，
    所有写操作均显式提交并刷新实例以同步数据库默认值。
    """

    def __init__(self, session: Session) -> None:
        """初始化仓储并注入会话。

        Args:
            session: SQLAlchemy 数据库会话。
        """
        self.session = session

    def create(self, payload: DataItemCreate) -> DataItem:
        """插入一条数据条目并返回刷新后的实例。

        Args:
            payload: 创建请求体。

        Returns:
            已持久化并刷新的 DataItem 实例。
        """
        item = DataItem(**payload.model_dump())
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def list(
        self,
        namespace: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DataItem]:
        """分页查询未软删的数据条目。

        Args:
            namespace: 可选命名空间过滤条件。
            limit: 单页最大条目数。
            offset: 查询偏移量。

        Returns:
            当前页的 DataItem 实例列表。
        """
        statement = select(DataItem).where(DataItem.deleted_at.is_(None))
        if namespace:
            statement = statement.where(DataItem.namespace == namespace)
        statement = (
            statement
            .order_by(DataItem.created_at.desc())
            .limit(limit)
            .offset(offset)
        )
        return list(self.session.scalars(statement))

    def count(self, namespace: str | None = None) -> int:
        """统计未软删的数据条目数量。

        Args:
            namespace: 可选命名空间过滤条件，为 None 时统计全量。

        Returns:
            符合条件的记录数，无数据时返回 0。
        """
        statement = select(func.count()).select_from(DataItem).where(DataItem.deleted_at.is_(None))
        if namespace:
            statement = statement.where(DataItem.namespace == namespace)
        return self.session.scalar(statement) or 0

    def get(self, item_id: UUID) -> DataItem | None:
        """按 ID 查询未软删的数据条目。

        Args:
            item_id: 数据条目唯一标识。

        Returns:
            命中的 DataItem 实例，不存在时返回 None。
        """
        statement = select(DataItem).where(
            DataItem.id == item_id,
            DataItem.deleted_at.is_(None),
        )
        return self.session.scalar(statement)

    def update(self, item: DataItem, payload: DataItemUpdate) -> DataItem:
        """按显式字段更新数据条目。

        Args:
            item: 待更新的 DataItem 实例。
            payload: 仅包含待更新字段的请求体。

        Returns:
            更新并刷新后的 DataItem 实例。
        """
        update_data = payload.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(item, key, value)
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def soft_delete(self, item: DataItem) -> None:
        """软删除指定数据条目，写入 deleted_at 时间戳。

        Args:
            item: 待软删除的 DataItem 实例。
        """
        item.deleted_at = datetime.now(UTC)
        self.session.add(item)
        self.session.commit()
