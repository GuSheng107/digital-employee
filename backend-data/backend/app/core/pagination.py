"""backend-data 统一分页计算、SQL 查询与响应构造。"""

from __future__ import annotations

from collections.abc import Sequence
from dataclasses import dataclass
from typing import Any, Generic, TypeVar

from sqlalchemy import Select, func, select
from sqlalchemy.orm import Session

T = TypeVar("T")


@dataclass(frozen=True, slots=True)
class PageSpec:
    """分页请求的规范化页码与每页条数。"""

    page: int
    page_size: int

    @property
    def offset(self) -> int:
        """返回 SQL/序列分页偏移量。"""
        return (self.page - 1) * self.page_size


@dataclass(frozen=True, slots=True)
class PageSlice(Generic[T]):
    """数据层分页查询结果。"""

    items: list[T]
    total: int
    spec: PageSpec

    def response(self, items: list[Any] | None = None) -> dict[str, Any]:
        """构造项目统一的分页响应字段。"""
        return {
            "items": self.items if items is None else items,
            "total": self.total,
            "page": self.spec.page,
            "page_size": self.spec.page_size,
        }


def paginate_scalars(
    session: Session,
    statement: Select[tuple[T]],
    spec: PageSpec,
) -> PageSlice[T]:
    """对 SQLAlchemy 单实体查询统一统计并分页。"""
    count_statement = select(func.count()).select_from(
        statement.order_by(None).subquery()
    )
    total = session.scalar(count_statement) or 0
    items = list(
        session.scalars(statement.offset(spec.offset).limit(spec.page_size))
    )
    return PageSlice(items=items, total=total, spec=spec)


def paginate_sequence(items: Sequence[T], spec: PageSpec) -> PageSlice[T]:
    """对 Redis 等已加载序列应用同一分页响应协议。"""
    page_items = list(items[spec.offset : spec.offset + spec.page_size])
    return PageSlice(items=page_items, total=len(items), spec=spec)
