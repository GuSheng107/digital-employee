from __future__ import annotations

from pydantic import BaseModel, Field

from app.memory_schema import MemoryItem, RetrievalHints, ContentType


class ExplicitMemoryItem(BaseModel):
    content: str = ""
    content_type: ContentType = "fact"
    speed_lookup: str = ""
    retrieval: RetrievalHints = Field(default_factory=RetrievalHints)


class ExplicitMemoryResult(BaseModel):
    summary: str = ""
    explicit_memories: list[ExplicitMemoryItem] = Field(default_factory=list)
    profile_candidates: list[ExplicitMemoryItem] = Field(default_factory=list)
    work_facts: list[ExplicitMemoryItem] = Field(default_factory=list)
    timeline_items: list[ExplicitMemoryItem] = Field(default_factory=list)
