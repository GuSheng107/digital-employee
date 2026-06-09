from __future__ import annotations

from pydantic import BaseModel, Field

from app.memory_schema import MemoryItem


class MemoryCandidate(BaseModel):
    category: str = "explicit"
    item: MemoryItem = Field(default_factory=MemoryItem)
    confidence: float = 1.0
    target_file: str = ""
