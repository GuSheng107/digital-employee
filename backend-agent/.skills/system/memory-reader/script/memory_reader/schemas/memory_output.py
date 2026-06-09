from __future__ import annotations

from pydantic import BaseModel, Field

from app.memory_schema import MemoryItem


class MemoryOutput(BaseModel):
    items: list[MemoryItem] = Field(default_factory=list)
    total_tokens: int = 0
    query: str = ""
    file_stats: dict[str, int] = Field(default_factory=dict)
    memory_pack: str = ""
    selected_files: list[str] = Field(default_factory=list)
    selected_sections: list[str] = Field(default_factory=list)
    omitted_files: list[str] = Field(default_factory=list)
    token_budget_used_estimate: int = 0
    confidence: str = ""
    needs_more_memory: bool = False
    reason: str = ""
