from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.llm_usage import resolve_token_usage
from app.memory_schema import MemoryItem

logger = logging.getLogger(__name__)

PROMOTE_SYSTEM = """You are the memory promotion module. Your task is to review items and decide their proper placement.

## File categories
- explicit: Direct instructions, rules, Q&A, facts the user wants remembered (priority 10)
- profile: User preferences, habits, personal traits (priority 6)
- work: Business facts, technical decisions, project knowledge (priority 8)
- inbox: Unresolved items needing review (priority 2)
- timeline: Time-bound events, archived items (priority 4)

## Rules
- Each item must be assigned to exactly one target file.
- Set priority based on importance and likelihood of being queried.
- Update content_type if the current one is wrong. Valid values: "problem_solution", "qa", "term_definition", "operation_guide", "configuration", "process", "rule", "fact", "preference", "comparison".
- Keep speed_lookup and retrieval as-is unless they need improvement.
- Return JSON only.

## Items to promote:
{items_json}

Return JSON:
{{
  "promotions": [
    {{
      "item_id": "...",
      "target_file": "explicit",
      "priority": 10.0,
      "content_type": "problem_solution",
      "reason": "why this placement"
    }}
  ]
}}"""


class PromotionAction(BaseModel):
    item_id: str = ""
    target_file: str = "inbox"
    priority: float = 2.0
    content_type: str = "fact"
    reason: str = ""


class PromoteResult(BaseModel):
    promotions: list[PromotionAction] = Field(default_factory=list)
    token_usage: dict[str, int] = Field(default_factory=dict)
    token_usage_source: str = ""
    llm_error: str = ""


def _get_llm(llm: BaseChatModel | None = None) -> BaseChatModel:
    if llm is not None:
        return llm
    import os
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY not set; cannot initialize default LLM")
    return ChatOpenAI(temperature=0)


def _items_to_json(items: list[MemoryItem]) -> str:
    data = []
    for item in items:
        data.append({
            "id": item.id,
            "content": item.content,
            "content_type": item.content_type,
            "speed_lookup": item.speed_lookup,
            "priority": item.priority,
            "source": item.source,
            "created_at": item.created_at,
            "retrieval": item.retrieval.model_dump(),
        })
    return json.dumps(data, ensure_ascii=False, indent=2)


def run_promote_chain(
    llm: BaseChatModel,
    items: list[MemoryItem],
) -> PromoteResult:
    model = _get_llm(llm)
    parser = JsonOutputParser(pydantic_object=PromoteResult)
    prompt = ChatPromptTemplate.from_template(PROMOTE_SYSTEM, template_format="f-string")

    items_json = _items_to_json(items)

    prompt_value: Any = ""
    response: Any = None
    try:
        prompt_value = prompt.invoke(
            {
                "items_json": items_json,
                "format_instructions": parser.get_format_instructions(),
            }
        )
        response = model.invoke(prompt_value)
        token_usage, token_usage_source = resolve_token_usage(response, prompt_value)
        raw = parser.invoke(response)

        promotions: list[PromotionAction] = []
        for p in raw.get("promotions", []):
            promotions.append(PromotionAction(
                item_id=p.get("item_id", ""),
                target_file=p.get("target_file", "inbox"),
                priority=float(p.get("priority", 2.0)),
                content_type=p.get("content_type", "fact"),
                reason=p.get("reason", ""),
            ))

        return PromoteResult(
            promotions=promotions,
            token_usage=token_usage,
            token_usage_source=token_usage_source,
        )
    except Exception as exc:
        logger.warning("Promote chain failed: %s", exc)
        token_usage, token_usage_source = (
            resolve_token_usage(response, prompt_value) if response is not None else ({}, "")
        )
        return PromoteResult(
            promotions=[],
            token_usage=token_usage,
            token_usage_source=token_usage_source,
            llm_error=str(exc),
        )
