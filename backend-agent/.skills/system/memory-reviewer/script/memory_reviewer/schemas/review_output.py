from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field

from memory_reviewer.schemas.issue import Issue
from memory_reviewer.schemas.patch import Patch
from memory_reviewer.schemas.conflict import Conflict


class ReviewOutput(BaseModel):
    review_summary: str = ""
    quality_score: int = 0
    issues: list[Issue] = Field(default_factory=list)
    recommended_patches: list[Patch] = Field(default_factory=list)
    compress_suggestions: list[Any] = Field(default_factory=list)
    promote_suggestions: list[Any] = Field(default_factory=list)
    items_to_merge: list[str] = Field(default_factory=list)
    items_to_delete: list[str] = Field(default_factory=list)
    items_to_deprecate: list[str] = Field(default_factory=list)
    items_to_move_to_inbox: list[str] = Field(default_factory=list)
    items_to_compress: list[str] = Field(default_factory=list)
    missing_memory_warnings: list[str] = Field(default_factory=list)
    conflicts: list[Conflict] = Field(default_factory=list)
    changelog_items: list[str] = Field(default_factory=list)
    safe_to_apply: bool = False
    token_usage: dict[str, int] = Field(default_factory=dict)
    boundary_metrics: dict[str, Any] = Field(default_factory=dict)
