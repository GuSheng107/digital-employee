from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.llm_usage import resolve_token_usage
from memory_reviewer.schemas.patch import Patch
from memory_reviewer.chains.common import format_memory_files

logger = logging.getLogger(__name__)

FEEDBACK_REPAIR_SYSTEM = """You are the feedback repair module of memory-reviewer. You are the SOLE decision-maker for converting user feedback into memory repairs. There are NO algorithmic checkers — you must analyze and fix ALL issues yourself.

## Your Task
Convert user correction or deletion requests into memory repair patches.

## Core Principles
- Do not invent facts.
- Only use the provided user feedback and memory files.
- User feedback ALWAYS overrides historical memory. If the user says something is wrong, it is wrong — do not defend existing memory.
- Preserve Chinese memory content unless the source is English.
- Return JSON only.

## Analysis Steps

### Step 1: Understand the Feedback
Determine what the user is telling you:
- **Correction**: "X should be Y, not Z" → update the memory item
- **Deletion**: "Remove X" or "X is no longer relevant" → delete the memory item
- **Addition**: "Also remember X" → add new memory item
- **Merge**: "These two items are about the same thing" → merge into one
- **Speed lookup fix**: "The search keywords for X are wrong" → update 速查词

### Step 2: Locate Affected Memory
- Search ALL memory files for items related to the feedback.
- Match by item content and ID, not just exact text. The user may describe the item differently.
- If you can't find the exact item, find the closest match and note the discrepancy.

### Step 3: Generate Patches
Memory files are stored as JSON. Each file contains a list of items with unique IDs.
Agent-first repair rule: when feedback shows that memory content is wrong, incomplete, outdated, fragmented, or hard to retrieve, generate a patch that directly fixes the affected memory item. The patch applier preserves fields omitted from `new_item`, so include only fields that should change.
Allowed `new_item` fields for update/compress/promote patches: `content`, `content_type`, `speed_lookup`, `retrieval`, `source`, `source_id`, `priority`.
For each affected item, generate a patch. For content fixes, include corrected `content` and any related fields that should change. For speed_lookup-only fixes, set `new_item` to only {{"speed_lookup": "..."}} and do not rewrite content or content_type. When `content_type` is present, it MUST be one of: "problem_solution", "qa", "term_definition", "operation_guide", "configuration", "process", "rule", "fact", "preference", "comparison".

**Update patch** (correct content or fix 速查词):
```json
{{
  "patch_id": "fb-1",
  "target_file": "explicit",
  "action": "update",
  "item_id": "item-abc-123",
  "source_ids": [],
  "new_item": {{
    "content": "the corrected content",
    "content_type": "problem_solution",
    "speed_lookup": "keyword1|keyword2|keyword3",
    "retrieval": {{"entities": [], "terms": [], "aliases": [], "keywords": []}}
  }},
  "reason": "用户反馈: ...",
  "confidence": "high",
  "requires_user_confirmation": false
}}
```

For a 速查词-only update, prefer the narrower patch:
```json
{{
  "patch_id": "fb-lookup-1",
  "target_file": "explicit",
  "action": "update",
  "item_id": "item-abc-123",
  "source_ids": [],
  "new_item": {{
    "speed_lookup": "keyword1|keyword2|keyword3"
  }},
  "reason": "用户反馈: 速查词无法命中",
  "confidence": "high",
  "requires_user_confirmation": false
}}
```

**Delete patch** (remove incorrect/irrelevant items):
```json
{{
  "patch_id": "fb-2",
  "target_file": "explicit",
  "action": "delete",
  "item_id": "item-abc-456",
  "source_ids": [],
  "new_item": null,
  "reason": "用户要求删除: ...",
  "confidence": "high",
  "requires_user_confirmation": true
}}
```

**Add patch** (add new memory from feedback):
```json
{{
  "patch_id": "fb-3",
  "target_file": "explicit",
  "action": "add",
  "item_id": "",
  "source_ids": [],
  "new_item": {{
    "content": "事实: ...",
    "content_type": "fact",
    "speed_lookup": "keyword1|keyword2|keyword3",
    "retrieval": {{"entities": [], "terms": [], "aliases": [], "keywords": []}}
  }},
  "reason": "用户要求新增记忆: ...",
  "confidence": "high",
  "requires_user_confirmation": false
}}
```

**Merge patch** (combine fragmented items):
```json
{{
  "patch_id": "fb-4",
  "target_file": "explicit",
  "action": "merge",
  "item_id": "",
  "source_ids": ["item-abc-789", "item-abc-012"],
  "new_item": {{
    "content": "问题: item one | 原因/解决: item two",
    "content_type": "problem_solution",
    "speed_lookup": "a|b|c|d",
    "retrieval": {{"entities": [], "terms": [], "aliases": [], "keywords": []}}
  }},
  "reason": "用户反馈这两条是同一条信息的不同部分",
  "confidence": "high",
  "requires_user_confirmation": true
}}
```

### Step 4: 速查词 Quality
When generating or updating 速查词, follow these rules:
- Each keyword must be a semantically complete Chinese word or compound (2-6 chars)
- NEVER break words in the middle (e.g., "入库单" must not become "入库" + "单")
- Include domain terms, abbreviations, and compound nouns
- Exclude stop words: 的,了,是,在,有,可能,原因,或者,如果,需要,可以
- 3-8 keywords per item, pipe-separated

## User feedback:
{user_feedback}

## Current message:
{current_message}

## Memory files (JSON format):
{memory_files}

{format_instructions}"""


class _FeedbackRepairOutput(BaseModel):
    affected_items: list[Any] = Field(default_factory=list)
    recommended_patches: list[Any] = Field(default_factory=list)
    items_to_delete: list[str] = Field(default_factory=list)
    items_to_move_to_inbox: list[str] = Field(default_factory=list)
    changelog_items: list[str] = Field(default_factory=list)
    requires_user_confirmation: bool = True


def _get_llm(llm: BaseChatModel | None = None) -> BaseChatModel:
    if llm is not None:
        return llm
    import os
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY not set; cannot initialize default LLM")
    return ChatOpenAI(temperature=0)


def run_feedback_repair_chain(
    user_feedback: str,
    memory_files: dict[str, str],
    current_message: str = "",
    llm: BaseChatModel | None = None,
) -> dict[str, Any]:
    model = _get_llm(llm)
    parser = JsonOutputParser(pydantic_object=_FeedbackRepairOutput)
    prompt = ChatPromptTemplate.from_template(
        FEEDBACK_REPAIR_SYSTEM, template_format="f-string"
    )

    files_text = format_memory_files(memory_files)

    prompt_value: Any = ""
    response: Any = None
    try:
        prompt_value = prompt.invoke(
            {
                "user_feedback": user_feedback,
                "current_message": current_message or "(none)",
                "memory_files": files_text,
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
        logger.warning("Feedback repair chain failed: %s", exc)
        token_usage, token_usage_source = (
            resolve_token_usage(response, prompt_value) if response is not None else ({}, "")
        )
        return {
            "affected_items": [],
            "recommended_patches": [],
            "items_to_delete": [],
            "items_to_move_to_inbox": [],
            "changelog_items": [],
            "requires_user_confirmation": True,
            "token_usage": token_usage,
            "token_usage_source": token_usage_source,
            "llm_error": str(exc),
        }
