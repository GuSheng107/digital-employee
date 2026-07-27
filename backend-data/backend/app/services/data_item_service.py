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

    def list(
        self,
        namespace: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DataItem]:
        return self.repository.list(namespace=namespace, limit=limit, offset=offset)

    def list_with_count(
        self,
        namespace: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> tuple[list[DataItem], int]:
        """分页查询并返回 (items, total)。

        Args:
            namespace: 可选命名空间过滤条件，为 None 时不过滤。
            limit: 单页最大条目数，默认 50。
            offset: 查询偏移量，默认 0。

        Returns:
            二元组 (当前页数据条目列表, 符合过滤条件的总数)。
        """
        items = self.repository.list(namespace=namespace, limit=limit, offset=offset)
        total = self.repository.count(namespace=namespace)
        return items, total

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
