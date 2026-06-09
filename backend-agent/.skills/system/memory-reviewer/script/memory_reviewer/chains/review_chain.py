from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.messages import SystemMessage
from langchain_core.output_parsers import JsonOutputParser
from langchain_openai import ChatOpenAI
from pydantic import BaseModel, Field

from app.llm_usage import content_text, extract_token_usage, resolve_token_usage
from memory_reviewer.schemas.review_output import ReviewOutput
from memory_reviewer.chains.common import format_memory_files

logger = logging.getLogger(__name__)

_USAGE_CONTAINER_KEYS = (
    "usage_metadata",
    "response_metadata",
    "additional_kwargs",
    "model_extra",
    "token_usage",
    "usage",
)
_INPUT_TOKEN_KEYS = (
    "input_tokens",
    "prompt_tokens",
    "input_token_count",
    "prompt_token_count",
    "input",
    "prompt",
)
_OUTPUT_TOKEN_KEYS = (
    "output_tokens",
    "completion_tokens",
    "output_token_count",
    "completion_token_count",
    "output",
    "completion",
)
_TOTAL_TOKEN_KEYS = (
    "total_tokens",
    "total_token_count",
    "tokens",
)
_ALL_TOKEN_KEYS = set(_INPUT_TOKEN_KEYS + _OUTPUT_TOKEN_KEYS + _TOTAL_TOKEN_KEYS)
_PROMPT_VARIABLES = (
    "review_type",
    "current_message",
    "agent_answer",
    "user_feedback",
    "memory_pack",
    "memory_files",
    "format_instructions",
)


def _as_mapping(value: Any) -> dict[str, Any] | None:
    if isinstance(value, dict):
        return value
    if hasattr(value, "model_dump"):
        try:
            dumped = value.model_dump()
        except Exception:
            dumped = None
        if isinstance(dumped, dict):
            return dumped
    return None


def _coerce_int(value: Any) -> int:
    if isinstance(value, bool) or value is None:
        return 0
    try:
        return max(0, int(value))
    except (TypeError, ValueError):
        try:
            return max(0, int(float(str(value).strip())))
        except (TypeError, ValueError):
            return 0


def _first_token_value(mapping: dict[str, Any], keys: tuple[str, ...]) -> int:
    for key in keys:
        if key in mapping:
            value = _coerce_int(mapping.get(key))
            if value:
                return value
    return 0


def _iter_usage_mappings(value: Any, seen: set[int] | None = None):
    if value is None:
        return
    if seen is None:
        seen = set()
    value_id = id(value)
    if value_id in seen:
        return
    seen.add(value_id)

    mapping = _as_mapping(value)
    if mapping is not None:
        if any(key in mapping for key in _ALL_TOKEN_KEYS):
            yield mapping
        for key in _USAGE_CONTAINER_KEYS:
            if key in mapping:
                yield from _iter_usage_mappings(mapping.get(key), seen)
        return

    attr_usage: dict[str, Any] = {}
    for key in _ALL_TOKEN_KEYS:
        if hasattr(value, key):
            attr_usage[key] = getattr(value, key)
    if attr_usage:
        yield attr_usage

    for attr in _USAGE_CONTAINER_KEYS:
        nested = getattr(value, attr, None)
        if nested is not None:
            yield from _iter_usage_mappings(nested, seen)


def _message_content_text(message: Any) -> str:
    return content_text(message)


def _estimate_text_tokens(text: str) -> int:
    value = str(text or "").strip()
    if not value:
        return 0
    return max(1, (len(value) + 3) // 4)


def _estimate_token_usage(prompt_text: str, response: Any) -> dict[str, int]:
    input_tokens = _estimate_text_tokens(prompt_text)
    output_tokens = _estimate_text_tokens(_message_content_text(response))
    total_tokens = input_tokens + output_tokens
    if total_tokens <= 0:
        return {}
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _extract_token_usage(message: Any) -> dict[str, int]:
    return extract_token_usage(message)


def _render_review_prompt(values: dict[str, Any]) -> str:
    rendered = REVIEW_SYSTEM.replace("{{", "{").replace("}}", "}")
    for name in _PROMPT_VARIABLES:
        rendered = rendered.replace("{" + name + "}", str(values.get(name, "")))
    return rendered


REVIEW_SYSTEM = """You are the review module of memory-reviewer. You must detect all semantic quality issues from the provided memory context. Deterministic safety checks may also run after your review, but you should not rely on them to notice semantic problems.

## General Rules
- Do not invent facts.
- Only use the provided memory files, Memory Pack, current message, agent answer, and user feedback.
- Memory content should remain Chinese unless the source is English.
- Final review_summary, issue descriptions, patch reasons, and all human-facing review text must be written in Chinese.
- Return JSON only.
- Priority order for conflicts: current user instruction > explicit/admin-config memory > document memory > chat/session memory > profile/timeline/inbox.
- Priority order for duplicate cleanup: explicit/admin-config memory > document memory > chat/session memory. Keep the highest-tier duplicate and delete the lower-tier duplicate.

## Review type: {review_type}

---

## SCENARIO A: memory_files — Full Memory Store Audit

When review_type is "memory_files", perform a comprehensive audit of ALL memory files.

### A1. Duplicate Detection
- Find items that convey the SAME information across or within files.
- Two items are duplicates if they answer the same question or state the same fact, even with different wording.
- Example duplicate: "销发分离: 销售店铺跟发货仓库不同" and "销发分离是指销售店铺与发货仓库不是同一个" — same meaning, different wording.

### A1b. Tiered Source Priority Dedup
- If a non-explicit memory item conveys the SAME information as explicit/admin-config memory, generate a "delete" patch for the non-explicit item.
- If a chat/session memory item conveys the SAME information as document memory, generate a "delete" patch for the chat/session item.
- NEVER generate a "delete" patch for any item in explicit/admin-config memory. Explicit memory is user-authored and must be preserved.
- Example: explicit has "销发分离: 销售店铺跟发货仓库不同" and work has "术语: 销发分离" → delete the work item, keep the explicit item.
- Example: documents/doc-a has "采购退货单从聚水潭拉取" and work/timeline chat item repeats it → delete the chat/session item, keep the document item.
- In review mode (not patch), report these as issues with category "duplicate" and describe the priority relation in Chinese.

### A2. Conflict Detection
- Find items that CONTRADICT each other.
- Example conflict: "库存管控: 已开启" vs "库存管控: 已关闭"
- Classify conflict_type: direct_contradiction | outdated | scope_mismatch | priority_conflict

### A3. 速查词 (Speed Lookup) Quality Check — VERY IMPORTANT
Every memory item may have a speed_lookup field. Check each one:

GOOD 速查词:
- "入库单|库存|推送|库存不变|不管控库存" — complete words, semantically meaningful
- "销发分离|销售店铺|发货仓库" — proper Chinese word boundaries
- "ERP|采购订单|全局设置" — includes abbreviations and compound nouns

BAD 速查词 (flag as issue category "bad_speed_lookup"):
- "销发分离是指|销售店铺跟发|货仓库不是同|一个" — words broken in the middle!
- "推送了入库|单到店家" — "入库单" split into "入库" + "单到店家"
- "的|了|是|在" — stop words, never valid keywords
- Single characters as keywords
- Too long (>8 chars per keyword) or too short (1 char)
- Missing obvious important terms from the content

### A4. Fragmented Memory Detection
- Find items that were incorrectly split from a single piece of information.
- Example: "聚水潭推送了入库单到店家但库存没有变动" and "erp设置了不管控库存" should be ONE item: "问题: 聚水潭推送了入库单到店家但库存没有变动 | 原因/解决: erp设置了不管控库存"
- Flag as category "fragmented_memory"

### A5. Outdated Memory
- Items that reference past states no longer current (e.g., "计划下周做X" but that week has passed).
- Flag as category "outdated"

### A6. Low-Value Memory
- Trivial information unlikely to be queried again (e.g., "今天天气不错", "好的").
- Flag as category "low_value"

### A7. Missing Memory
- Important files (explicit, profile) that are empty.
- Flag as category "missing_memory"

### A8. Excessive Length
- Flag only when a single item is unnecessarily verbose, repetitive, or mixes unrelated details and can be shortened without losing useful information.
- Length alone is not a defect. Long but unique, useful, and precise memory should be preserved.
- Flag as category "excessive_length"

---

## SCENARIO B: memory_pack — Runtime Memory Pack Review

When review_type is "memory_pack", evaluate the Memory Pack that was injected into a conversation.

### B1. Relevance Check
- Was the memory pack relevant to the current_message?
- Were critical memories missing that should have been included?
- Was irrelevant memory injected that wasted tokens?

### B2. Completeness Check
- If the agent_answer was wrong or incomplete, was it because relevant memory was missing from the pack?
- Check if explicit memory items relevant to the question were included.

### B3. 速查词 Effectiveness
- If the pack missed relevant memory, check if the 速查词 in the source files would have matched the query.
- If 速查词 are bad, flag as "bad_speed_lookup" issue.

### B4. User Feedback Integration
- If user_feedback says the answer was useless/无用, treat it as a high-priority failure signal.
- Determine if the error was due to missing memory, wrong memory, bad retrieval, bad 速查词, or irrelevant memory injection.
- Generate patches to fix the root cause whenever the provided context supports a safe fix.
- If user_feedback says the answer was useful/有用, treat it as positive evidence, not as a repair request.

---

## Patch Generation Rules

Memory files are stored as JSON. Each file contains a list of items with unique IDs (UUIDs like "6369bf31-e666-4327-915f-632139a1259c").
Agent-first repair rule: when memory content is wrong, incomplete, outdated, fragmented, overlong, or hard to retrieve, generate a patch that directly fixes the memory item. The patch applier will preserve fields that are not present in `new_item`, so include only fields that should change.
Allowed `new_item` fields for update/compress/promote patches: `content`, `content_type`, `speed_lookup`, `retrieval`, `source`, `source_id`, `priority`.
Use full-content rewrites when the content itself is wrong or incomplete. Use narrow field-only patches when only metadata or retrieval hints need repair.

When you find issues, generate patches to fix them. Each patch MUST include:

1. **patch_id**: Unique identifier like "p-1", "p-2"
2. **target_file**: Which memory file to modify (e.g., "explicit", "profile", "work")
3. **action**: One of:
   - "update" — update an existing item's content, speed_lookup, or retrieval
   - "delete" — remove the item entirely (duplicates, low-value, outdated)
   - "merge" — combine two or more items into one (fragmented memory)
   - "archive" — move item to timeline (outdated but worth keeping)
   - "promote" — move item to a different file (wrong placement)
   - "compress" — shorten an unnecessarily verbose or repetitive item without losing useful information
   - "add" — add new missing memory
4. **item_id**: The EXACT "id" field value of the target item from the JSON (for update, delete, archive, compress). You MUST copy the full UUID exactly as it appears in the memory file — do NOT abbreviate, truncate, or invent IDs.
5. **source_ids**: List of item IDs to merge (for merge action). Same rule: copy full UUIDs exactly.
6. **new_item**: The replacement/new item data (for add, merge, update, compress, promote). For content fixes, include corrected `content` and any related fields that should change. For speed_lookup-only fixes, set `new_item` to only `{"speed_lookup": "..."}` and do not rewrite content or content_type. When `content_type` is present, it MUST be one of: "problem_solution", "qa", "term_definition", "operation_guide", "configuration", "process", "rule", "fact", "preference", "comparison".
7. **reason**: Why this patch is needed
8. **confidence**: "high" | "medium" | "low"
9. **requires_user_confirmation**: Set to false for ALL patches. The system will handle safety checks automatically.

### Patch Examples:

Fix bad 速查词:
```json
{{
  "patch_id": "p-1",
  "target_file": "explicit",
  "action": "update",
  "item_id": "6369bf31-e666-4327-915f-632139a1259c",
  "source_ids": [],
  "new_item": {{
    "speed_lookup": "销发分离|销售店铺|发货仓库"
  }},
  "reason": "速查词在词语中间断开，应保持完整词语边界",
  "confidence": "high",
  "requires_user_confirmation": false
}}
```

Fix wrong or incomplete content:
```json
{{
  "patch_id": "p-content-1",
  "target_file": "work",
  "action": "update",
  "item_id": "6369bf31-e666-4327-915f-632139a1259c",
  "source_ids": [],
  "new_item": {{
    "content": "问题: 聚水潭推送商品提示类目不存在 | 处理: 检查 OMS 设置-授权管理-聚水潭-规格模板是否填写服装，并核对店家类目与聚水潭类目是否对应",
    "content_type": "problem_solution",
    "speed_lookup": "聚水潭|推送商品|类目不存在|规格模板|店家类目"
  }},
  "reason": "原记忆缺少完整处理路径，应直接修正内容并同步速查词",
  "confidence": "high",
  "requires_user_confirmation": false
}}
```

Merge fragmented items:
```json
{{
  "patch_id": "p-2",
  "target_file": "work",
  "action": "merge",
  "item_id": "",
  "source_ids": ["a1b2c3d4-e5f6-7890-abcd-ef1234567890", "f9e8d7c6-b5a4-3210-fedc-ba0987654321"],
  "new_item": {{
    "content": "问题: 聚水潭推送了入库单到店家但库存没有变动 | 原因/解决: erp设置了不管控库存",
    "content_type": "problem_solution",
    "speed_lookup": "入库单|库存|推送|库存不变|不管控库存|ERP",
    "retrieval": {{"entities": [], "terms": [], "aliases": [], "keywords": []}}
  }},
  "reason": "因果关系被拆成两条，应合并为一条",
  "confidence": "high",
  "requires_user_confirmation": false
}}
```

Delete duplicate:
```json
{{
  "patch_id": "p-3",
  "target_file": "work",
  "action": "delete",
  "item_id": "11223344-5566-7788-99aa-bbccddeeff00",
  "source_ids": [],
  "new_item": null,
  "reason": "与另一条重复",
  "confidence": "medium",
  "requires_user_confirmation": false
}}
```

---

## Issue Categories
Use these exact category values (write issue descriptions in Chinese):
- "duplicate" — 重复：相同信息出现多次
- "conflict" — 冲突：互相矛盾的信息
- "outdated" — 过期：不再适用的信息
- "wrong_promotion" — 放置不当：记忆被放在错误的文件或分区
- "excessive_length" — 冗长/重复：可安全收敛
- "missing_memory" — 缺失：重要记忆缺失
- "low_value" — 低价值：琐碎内容，不太可能被查询
- "token_over_budget" — 超出预算：记忆包超过 token 预算
- "chinese_not_preserved" — 中文未保留：中文内容被改为英文
- "bad_speed_lookup" — 速查词质量问题：词语被截断、停用词、缺失关键词
- "fragmented_memory" — 碎片化：同一信息被拆分到多条记忆中
---

## Current message:
{current_message}

## Agent answer:
{agent_answer}

## User feedback:
{user_feedback}

## Memory Pack:
{memory_pack}

## Memory files (JSON format):
{memory_files}

{format_instructions}"""


class _ReviewChainOutput(BaseModel):
    review_summary: str = ""
    quality_score: int = 0
    issues: list[Any] = Field(default_factory=list)
    recommended_patches: list[Any] = Field(default_factory=list)
    compress_suggestions: list[Any] = Field(default_factory=list)
    promote_suggestions: list[Any] = Field(default_factory=list)
    items_to_merge: list[str] = Field(default_factory=list)
    items_to_delete: list[str] = Field(default_factory=list)
    items_to_deprecate: list[str] = Field(default_factory=list)
    items_to_move_to_inbox: list[str] = Field(default_factory=list)
    items_to_compress: list[str] = Field(default_factory=list)
    missing_memory_warnings: list[str] = Field(default_factory=list)
    conflicts: list[Any] = Field(default_factory=list)
    changelog_items: list[str] = Field(default_factory=list)
    safe_to_apply: bool = False


def _get_llm(llm: BaseChatModel | None = None) -> BaseChatModel:
    if llm is not None:
        return llm
    import os
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY not set; cannot initialize default LLM")
    return ChatOpenAI(temperature=0)


def run_review_chain(
    review_type: str,
    memory_files: dict[str, str],
    current_message: str = "",
    agent_answer: str = "",
    memory_pack: str = "",
    user_feedback: str = "",
    llm: BaseChatModel | None = None,
) -> dict[str, Any]:
    model = _get_llm(llm)
    parser = JsonOutputParser(pydantic_object=_ReviewChainOutput)
    files_text = format_memory_files(memory_files)
    prompt_text = _render_review_prompt(
        {
            "review_type": review_type,
            "current_message": current_message or "(none)",
            "agent_answer": agent_answer or "(none)",
            "user_feedback": user_feedback or "(none)",
            "memory_pack": memory_pack or "(none)",
            "memory_files": files_text,
            "format_instructions": parser.get_format_instructions(),
        }
    )

    response: Any = None
    token_usage: dict[str, int] = {}
    token_usage_source = ""
    try:
        response = model.invoke([SystemMessage(content=prompt_text)])
        token_usage, token_usage_source = resolve_token_usage(response, prompt_text)
        result = parser.invoke(response)
        if isinstance(result, dict):
            result["token_usage"] = token_usage
            result["token_usage_source"] = token_usage_source
            result["llm_review_trace"] = {
                "review_type": review_type,
                "token_usage": token_usage,
                "token_usage_source": token_usage_source,
                "response_preview": _message_content_text(response)[:4000],
            }
        return result
    except Exception as exc:
        logger.warning("LLM review chain failed: %s", exc)
        trace = {
            "review_type": review_type,
            "error": str(exc),
            "token_usage": token_usage,
            "token_usage_source": token_usage_source,
        }
        if response is not None:
            trace["response_preview"] = _message_content_text(response)[:4000]
        return {
            "review_summary": f"[LLM 调用失败: {exc}]",
            "quality_score": 0,
            "issues": [],
            "recommended_patches": [],
            "compress_suggestions": [],
            "promote_suggestions": [],
            "items_to_merge": [],
            "items_to_delete": [],
            "items_to_deprecate": [],
            "items_to_move_to_inbox": [],
            "items_to_compress": [],
            "missing_memory_warnings": [],
            "conflicts": [],
            "changelog_items": [],
            "safe_to_apply": False,
            "token_usage": token_usage,
            "token_usage_source": token_usage_source,
            "llm_error": str(exc),
            "llm_review_trace": trace,
        }
