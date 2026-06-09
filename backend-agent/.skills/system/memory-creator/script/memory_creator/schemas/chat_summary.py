from __future__ import annotations

from pydantic import BaseModel, Field

from app.memory_schema import RetrievalHints, ContentType


class ChatMemoryItem(BaseModel):
    content: str = ""
    content_type: ContentType = "fact"
    speed_lookup: str = ""
    retrieval: RetrievalHints = Field(default_factory=RetrievalHints)


class ChatSummary(BaseModel):
    conversation_summary: str = ""
    explicit_memories: list[ChatMemoryItem] = Field(default_factory=list)
    profile_candidates: list[ChatMemoryItem] = Field(default_factory=list)
    business_facts: list[ChatMemoryItem] = Field(default_factory=list)
    decisions: list[ChatMemoryItem] = Field(default_factory=list)
    open_questions: list[ChatMemoryItem] = Field(default_factory=list)
    timeline_items: list[ChatMemoryItem] = Field(default_factory=list)
    inbox_items: list[ChatMemoryItem] = Field(default_factory=list)
