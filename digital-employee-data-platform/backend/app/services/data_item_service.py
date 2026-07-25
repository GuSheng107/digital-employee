from uuid import UUID

from fastapi import HTTPException

from app.models.data_item import DataItem
from app.repositories.data_item_repo import DataItemRepository
from app.schemas.data_item import DataItemCreate, DataItemUpdate


class DataItemService:
    def __init__(self, repository: DataItemRepository) -> None:
        self.repository = repository

    def create(self, payload: DataItemCreate) -> DataItem:
        return self.repository.create(payload)

    def list(self, namespace: str | None = None) -> list[DataItem]:
        return self.repository.list(namespace=namespace)

    def get(self, item_id: UUID) -> DataItem:
        item = self.repository.get(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="data item not found")
        return item

    def update(self, item_id: UUID, payload: DataItemUpdate) -> DataItem:
        item = self.get(item_id)
        return self.repository.update(item, payload)

    def delete(self, item_id: UUID) -> None:
        item = self.get(item_id)
        self.repository.soft_delete(item)
