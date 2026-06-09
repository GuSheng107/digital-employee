from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ConflictItem(BaseModel):
    file: str = ""
    text: str = ""
    priority: str = ""
    date: str = ""


class Conflict(BaseModel):
    conflict_id: str = ""
    items: list[ConflictItem] = Field(default_factory=list)
    conflict_type: Literal[
        "direct_contradiction", "outdated", "scope_mismatch", "priority_conflict"
    ] = "direct_contradiction"
    recommended_resolution: str = ""
    requires_user_confirmation: bool = True
