from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class Issue(BaseModel):
    issue_id: str = ""
    severity: Literal["high", "medium", "low"] = "medium"
    category: Literal[
        "duplicate", "conflict", "outdated", "wrong_promotion",
        "excessive_length", "missing_memory", "low_value",
        "token_over_budget", "chinese_not_preserved",
        "bad_speed_lookup", "fragmented_memory",
    ] = "duplicate"
    description: str = ""
    affected_files: list[str] = Field(default_factory=list)
    affected_text: str = ""
    suggestion: str = ""
