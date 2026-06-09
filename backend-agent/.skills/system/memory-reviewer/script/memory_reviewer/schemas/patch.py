from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

from app.memory_schema import MemoryItem


class Patch(BaseModel):
    patch_id: str = ""
    target_file: str = ""
    action: Literal["add", "update", "delete", "merge", "compress", "promote", "archive"] = "update"
    target_section: str = ""
    item_id: str = ""
    source_ids: list[str] = Field(default_factory=list)
    old_text: str = ""
    new_text: str = ""
    new_item: MemoryItem | None = None
    reason: str = ""
    confidence: Literal["high", "medium", "low"] = "medium"
    requires_user_confirmation: bool = True
