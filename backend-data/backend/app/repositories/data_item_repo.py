from datetime import UTC, datetime
from uuid import UUID

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.data_item import DataItem
from app.schemas.data_item import DataItemCreate, DataItemUpdate


class DataItemRepository:
    def __init__(self, session: Session) -> None:
        self.session = session

    def create(self, payload: DataItemCreate) -> DataItem:
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
        statement = select(func.count()).select_from(DataItem).where(DataItem.deleted_at.is_(None))
        if namespace:
            statement = statement.where(DataItem.namespace == namespace)
        return self.session.scalar(statement) or 0

    def get(self, item_id: UUID) -> DataItem | None:
        statement = select(DataItem).where(
            DataItem.id == item_id,
            DataItem.deleted_at.is_(None),
        )
        return self.session.scalar(statement)

    def update(self, item: DataItem, payload: DataItemUpdate) -> DataItem:
        update_data = payload.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            setattr(item, key, value)
        self.session.add(item)
        self.session.commit()
        self.session.refresh(item)
        return item

    def soft_delete(self, item: DataItem) -> None:
        item.deleted_at = datetime.now(UTC)
        self.session.add(item)
        self.session.commit()
