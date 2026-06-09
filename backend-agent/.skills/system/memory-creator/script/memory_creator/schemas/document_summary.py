from __future__ import annotations

from pydantic import BaseModel, Field

from app.memory_schema import RetrievalHints, ContentType


class LookupItem(BaseModel):
    key: str = ""
    value: str = ""
    category: str = ""
    source: str = ""
    speed_lookup: str = ""
    content_type: ContentType = "fact"
    retrieval: RetrievalHints = Field(default_factory=RetrievalHints)


class ChunkSummary(BaseModel):
    chunk_summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    business_facts: list[str] = Field(default_factory=list)
    rules_or_policies: list[str] = Field(default_factory=list)
    terms: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    project_memory_candidates: list[str] = Field(default_factory=list)
    lookup_items: list[LookupItem] = Field(default_factory=list)
    fallback_raw_text: str = ""
    retrieval_hints: RetrievalHints = Field(default_factory=RetrievalHints)


class DocumentSummary(BaseModel):
    document_summary: str = ""
    key_points: list[str] = Field(default_factory=list)
    business_facts: list[str] = Field(default_factory=list)
    rules_or_policies: list[str] = Field(default_factory=list)
    terms: list[str] = Field(default_factory=list)
    action_items: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    open_questions: list[str] = Field(default_factory=list)
    project_memory_candidates: list[str] = Field(default_factory=list)
    lookup_items: list[LookupItem] = Field(default_factory=list)
    fallback_raw_text: str = ""
    retrieval_hints: RetrievalHints = Field(default_factory=RetrievalHints)
