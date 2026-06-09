from __future__ import annotations

from pydantic import BaseModel, Field

from app.memory_schema import MemoryItem


class ConsolidationResult(BaseModel):
    source_type: str = ""
    source_id: str = ""
    updated_files: list[str] = Field(default_factory=list)
    memory_items: dict[str, list[MemoryItem]] = Field(default_factory=dict)
    summary: str = ""
    token_usage: dict[str, int] = Field(default_factory=dict)
