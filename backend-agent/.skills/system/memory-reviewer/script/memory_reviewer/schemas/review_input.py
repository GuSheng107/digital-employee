from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class ReviewMetadata(BaseModel):
    memory_root: str = ".memory"
    token_budget: int = 4000
    current_date: str = ""
    mode: Literal["review", "patch", "dry_run"] = "review"


class ReviewInput(BaseModel):
    review_type: Literal["memory_files", "memory_pack", "user_feedback", "scheduled_cleanup"]
    current_message: str = ""
    agent_answer: str = ""
    memory_pack: str = ""
    user_feedback: str = ""
    memory_files: dict[str, str] = Field(default_factory=dict)
    metadata: ReviewMetadata = Field(default_factory=ReviewMetadata)
