from __future__ import annotations

from uuid import UUID

from fastapi import HTTPException

from app.models.data_item import DataItem
from app.repositories.data_item_repo import DataItemRepository
from app.schemas.data_item import DataItemCreate, DataItemUpdate


class DataItemService:
    """数据条目业务编排层。

    封装数据条目的 CRUD 业务逻辑，对路由层屏蔽仓储细节。
    """

    def __init__(self, repository: DataItemRepository) -> None:
        """初始化服务并注入仓储实例。

        Args:
            repository: 数据条目仓储对象。
        """
        self.repository = repository

    def create(self, payload: DataItemCreate) -> DataItem:
        """创建一条新的数据条目。

        Args:
            payload: 创建请求体。

        Returns:
            持久化后的数据条目。
        """
        return self.repository.create(payload)

    def list(
        self,
        namespace: str | None = None,
        limit: int = 50,
        offset: int = 0,
    ) -> list[DataItem]:
        """分页查询数据条目列表。

        Args:
            namespace: 可选命名空间过滤条件，为 None 时不过滤。
            limit: 单页最大条目数，默认 50。
            offset: 查询偏移量，默认 0。

        Returns:
            当前页的数据条目列表。
        """
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
        """按 ID 查询单条数据条目。

        Args:
            item_id: 数据条目唯一标识。

        Returns:
            对应的数据条目。

        Raises:
            HTTPException: 条目不存在时返回 404。
        """
        item = self.repository.get(item_id)
        if item is None:
            raise HTTPException(status_code=404, detail="data item not found")
        return item

    def update(self, item_id: UUID, payload: DataItemUpdate) -> DataItem:
        """更新指定数据条目。

        Args:
            item_id: 待更新条目唯一标识。
            payload: 更新请求体，仅写入显式提供的字段。

        Returns:
            更新后的数据条目。
        """
        item = self.get(item_id)
        return self.repository.update(item, payload)

    def delete(self, item_id: UUID) -> None:
        """软删除指定数据条目。

        Args:
            item_id: 待删除条目唯一标识。
        """
        item = self.get(item_id)
        self.repository.soft_delete(item)
