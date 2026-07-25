from datetime import datetime
from typing import Any
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field


class DataItemBase(BaseModel):
    namespace: str = Field(min_length=1, max_length=100)
    item_key: str = Field(min_length=1, max_length=200)
    item_value: dict[str, Any] = Field(default_factory=dict)
    description: str = ""


class DataItemCreate(DataItemBase):
    pass


class DataItemUpdate(BaseModel):
    namespace: str | None = Field(default=None, min_length=1, max_length=100)
    item_key: str | None = Field(default=None, min_length=1, max_length=200)
    item_value: dict[str, Any] | None = None
    description: str | None = None


class DataItemRead(DataItemBase):
    model_config = ConfigDict(from_attributes=True)

    id: UUID
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None
