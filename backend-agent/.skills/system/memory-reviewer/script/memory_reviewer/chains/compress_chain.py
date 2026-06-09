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
from app.memory_schema import MemoryItem, ContentType

logger = logging.getLogger(__name__)

COMPRESS_SYSTEM = """You are the memory quality consolidation module. Your task is to review a memory file and consolidate only when there is a clear quality reason.

Memory is allowed to grow over time after regular review. Do not reduce size just because the file has many items, because an item is old, or because a shorter file would be convenient.

## Consolidation strategies
1. **merge**: Combine items that convey overlapping information into one item. The merged item's speed_lookup should include keywords from ALL source items.
2. **shorten**: Reduce verbose or repetitive content while keeping the key information. Update speed_lookup if needed.
3. **archive**: Move low-priority items to timeline only when they are no longer needed in the active file but remain useful for retrospective history.
4. **delete**: Remove truly redundant duplicates (same information already exists in another item). Only use when merge is not appropriate.

## Rules
- NEVER lose unique information. If in doubt, keep the item.
- Item count is an observation, not a trigger. A large file with unique, useful items should return no compressions.
- Age alone is not a reason to archive, shorten, or delete an item.
- Only act on duplicates, clear overlap, fragmented memory, low-value resolved content, or content that is unnecessarily verbose and can be shortened without information loss.
- When merging, the new content_type should be the most specific one from the source items. Valid content_type values: "problem_solution", "qa", "term_definition", "operation_guide", "configuration", "process", "rule", "fact", "preference", "comparison".
- When merging, combine all speed_lookup keywords (deduplicated, max 8).
- When merging, combine all retrieval hints.
- Archive only when the item is low-value for active retrieval but still useful as historical context.
- Return JSON only.

## Current file: {file_key}
Item count: {item_count}

## Items to review:
{items_json}

Return JSON:
{{
  "compressions": [
    {{
      "action": "merge|shorten|archive|delete",
      "source_ids": ["id1", "id2"],
      "new_item": {{
        "content": "...",
        "content_type": "problem_solution",
        "speed_lookup": "a|b|c",
        "retrieval": {{"entities": [], "terms": [], "aliases": [], "keywords": []}}
      }},
      "reason": "why this consolidation is necessary"
    }}
  ]
}}"""


class CompressionAction(BaseModel):
    action: str = "merge"
    source_ids: list[str] = Field(default_factory=list)
    new_item: MemoryItem | None = None
    reason: str = ""


class CompressResult(BaseModel):
    compressions: list[CompressionAction] = Field(default_factory=list)
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
            "created_at": item.created_at,
            "updated_at": item.updated_at,
            "retrieval": item.retrieval.model_dump(),
        })
    return json.dumps(data, ensure_ascii=False, indent=2)


def run_compress_chain(
    llm: BaseChatModel,
    file_key: str,
    items: list[MemoryItem],
) -> CompressResult:
    model = _get_llm(llm)
    parser = JsonOutputParser(pydantic_object=CompressResult)
    prompt = ChatPromptTemplate.from_template(COMPRESS_SYSTEM, template_format="f-string")

    items_json = _items_to_json(items)

    prompt_value: Any = ""
    response: Any = None
    try:
        prompt_value = prompt.invoke(
            {
                "file_key": file_key,
                "item_count": len(items),
                "items_json": items_json,
                "format_instructions": parser.get_format_instructions(),
            }
        )
        response = model.invoke(prompt_value)
        token_usage, token_usage_source = resolve_token_usage(response, prompt_value)
        raw = parser.invoke(response)

        compressions: list[CompressionAction] = []
        for c in raw.get("compressions", []):
            new_item = None
            ni = c.get("new_item")
            if ni and isinstance(ni, dict):
                ct = ni.get("content_type", "fact")
                if ct not in ContentType.__args__:
                    ct = "fact"
                new_item = MemoryItem(
                    content=ni.get("content", ""),
                    content_type=ct,
                    speed_lookup=ni.get("speed_lookup", ""),
                    retrieval=ni.get("retrieval", {}),
                )
            compressions.append(CompressionAction(
                action=c.get("action", "merge"),
                source_ids=c.get("source_ids", []),
                new_item=new_item,
                reason=c.get("reason", ""),
            ))

        return CompressResult(
            compressions=compressions,
            token_usage=token_usage,
            token_usage_source=token_usage_source,
        )
    except Exception as exc:
        logger.warning("Compress chain failed: %s", exc)
        token_usage, token_usage_source = (
            resolve_token_usage(response, prompt_value) if response is not None else ({}, "")
        )
        return CompressResult(
            compressions=[],
            token_usage=token_usage,
            token_usage_source=token_usage_source,
            llm_error=str(exc),
        )
