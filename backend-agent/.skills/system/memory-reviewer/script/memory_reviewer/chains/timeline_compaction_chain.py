from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.llm_usage import resolve_token_usage

logger = logging.getLogger(__name__)

TIMELINE_COMPACTION_SYSTEM = """You are the timeline retrospective consolidation module of memory-reviewer.

Your task is to review timeline entries and consolidate only redundant, low-value, or fragmented entries while preserving important facts.

Memory is allowed to grow after regular review. Do not compact timeline entries just because they are old or numerous.

Rules:
- Do not invent facts.
- Preserve explicit user decisions and constraints.
- Preserve project-critical information.
- Preserve Chinese memory content unless the source is English.
- Remove low-value entries (small talk, temporary instructions, already-resolved questions).
- Merge related entries about the same topic only when they duplicate or fragment the same information.
- Preserve old entries when they contain unique decisions, constraints, project context, or useful evidence.
- Keep the most recent version when entries conflict.
- Return JSON only.

Timeline text:
{timeline_text}

Current date:
{current_date}

{format_instructions}"""


class _TimelineCompactionOutput(BaseModel):
    compacted_text: str = ""
    removed_items: list[str] = Field(default_factory=list)
    merged_items: list[str] = Field(default_factory=list)
    preserved_items: list[str] = Field(default_factory=list)
    token_savings_estimate: int = 0


def _get_llm(llm: BaseChatModel | None = None) -> BaseChatModel:
    if llm is not None:
        return llm
    import os
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY not set; cannot initialize default LLM")
    return ChatOpenAI(temperature=0)


def run_timeline_compaction_chain(
    timeline_text: str,
    current_date: str = "",
    llm: BaseChatModel | None = None,
) -> dict[str, Any]:
    model = _get_llm(llm)
    parser = JsonOutputParser(pydantic_object=_TimelineCompactionOutput)
    prompt = ChatPromptTemplate.from_template(
        TIMELINE_COMPACTION_SYSTEM, template_format="f-string"
    )

    prompt_value: Any = ""
    response: Any = None
    try:
        prompt_value = prompt.invoke(
            {
                "timeline_text": timeline_text,
                "current_date": current_date or "(unknown)",
                "format_instructions": parser.get_format_instructions(),
            }
        )
        response = model.invoke(prompt_value)
        token_usage, token_usage_source = resolve_token_usage(response, prompt_value)
        result = parser.invoke(response)
        result["token_usage"] = token_usage
        result["token_usage_source"] = token_usage_source
        return result
    except Exception as exc:
        logger.warning("Timeline compaction chain failed: %s", exc)
        token_usage, token_usage_source = (
            resolve_token_usage(response, prompt_value) if response is not None else ({}, "")
        )
        return {
            "compacted_text": timeline_text,
            "removed_items": [],
            "merged_items": [],
            "preserved_items": [],
            "token_savings_estimate": 0,
            "token_usage": token_usage,
            "token_usage_source": token_usage_source,
            "llm_error": str(exc),
        }
