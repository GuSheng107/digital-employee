from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.llm_usage import extract_token_usage, resolve_token_usage
from memory_creator.schemas.document_summary import ChunkSummary, LookupItem
from app.memory_schema import RetrievalHints

logger = logging.getLogger(__name__)


def _extract_token_usage(message: Any) -> dict[str, int]:
    return extract_token_usage(message)


DOCUMENT_CHUNK_SYSTEM = """You are the document consolidation module of memory-creator.

Your task is to extract reusable, queryable information from the current chunk of a document.

## CRITICAL RULES (MUST FOLLOW)

1. **NO duplicate or near-duplicate items.** Before adding an item, check if a similar item already exists. If two items convey essentially the same fact, MERGE them into one. Example:
   - BAD: "支持MCP协议集成外部工具" AND "支持通过MCP协议接入外部工具服务" → these are the SAME fact
   - BAD: "跳过权限检查风险最高" AND "--dangerously-skip-permissions风险最高" → MERGE into one
2. **NEVER output a bare term/keyword as a standalone item.** Every item MUST be a self-contained, meaningful fact that a user could understand without context. Examples:
   - BAD: "REPL" (just a term, no meaning)
   - BAD: "沙箱隔离" (just a term, no meaning)
   - BAD: "权限模式" (just a term, no meaning)
   - GOOD: "REPL是Claw的交互式命令行模式，用于和AI连续多轮协作"
   - GOOD: "沙箱隔离机制保障命令执行边界安全，限制AI对系统的访问范围"
3. **Each item must be a SINGLE LINE without line breaks.** Combine related info using "|" separator.
4. **Every lookup_item MUST have a unique, item-specific `retrieval` object.** Do NOT copy the same retrieval across all items. Each item's entities, terms, aliases, keywords must relate to THAT specific item.
5. **Every lookup_item MUST have a non-empty `speed_lookup`** with 3-8 pipe-separated keywords specific to that item.
6. **Use only the current text chunk.** Do not invent information.
7. **Do not output the full raw text.** Extract concise, queryable facts.
8. **Technical keys must be English.** Actual memory values should be Chinese unless the source is English.

## lookup_items format

Each lookup_item must have:
- `key`: A concise, queryable question or keyword (e.g. "claw命令", "权限模式", "MCP集成")
- `value`: A concise answer or description (e.g. "启动交互式REPL", "只读/工作区可写/全权限三级")
- `category`: one of 政策 | 流程 | 规格 | 费用 | 联系信息 | 期限 | 限制 | 其他
- `source`: short excerpt from the source text (up to 100 chars)
- `speed_lookup`: pipe-separated 3-8 search keywords specific to THIS item (e.g. "claw命令|启动REPL|交互模式")
- `content_type`: one of problem_solution | qa | term_definition | operation_guide | configuration | process | rule | fact | preference
- `retrieval`: item-specific {{"entities": [], "terms": [], "aliases": [], "keywords": []}}

Aim for 5-20 items per chunk. Quality over quantity — each item must be unique and independently useful.

## speed_lookup rules

For each lookup_item, generate a speed_lookup string — pipe-separated 3-8 search keywords.
You MUST understand Chinese word boundaries. Each keyword must be a semantically complete word.

GOOD: "claw命令|启动REPL|交互模式|多轮协作"
BAD:  "启动了RE|PL交互模式|多轮协作的"

Rules:
- Each keyword: 2-6 characters for Chinese, any length for English
- Extract nouns, compound nouns, domain terms
- NEVER include: 的,了,是,在,有,可能,原因,或者,如果,需要,可以,什么,怎么,如何,一个,不是,但是
- NEVER include single characters
- **Sub-term extraction**: When a keyword is a compound noun ending with a company/product suffix (e.g., 科技, 公司, 集团, 平台, 系统), also include the core sub-term as a separate keyword. Example: "店家科技" → include both "店家科技" AND "店家"
- **Intent keywords**: Include keywords that reflect the user's search intent. For company/product info, include "公司介绍|企业介绍|产品体系|简介"; for operation guides, include "操作|步骤|流程"; for problems, include "问题|原因|解决"
- **Abbreviations**: Include common abbreviations or short forms users might search with (e.g., "店+" for "店家", "ERP" for "企业资源计划")

## retrieval rules (per item, NOT shared)

- entities: Named entities relevant to THIS item (product names, tool names, company names). Include sub-terms of compound names (e.g., for "店家科技", include both "店家科技" and "店家")
- terms: Domain-specific terms and technical concepts relevant to THIS item
- aliases: Alternative names, abbreviations, synonyms, short forms for THIS item. MUST include common abbreviations users might search with (e.g., "店+" for "店家科技")
- keywords: High-frequency search terms for THIS item. Include intent-related terms users might use when searching (e.g., "公司介绍", "企业介绍", "产品体系" for company info; "操作", "步骤" for guides)
- Keep each list concise (max 5 items per category)
- Do NOT include generic words or stop words

## key_points / business_facts / terms / rules_or_policies rules

These fields contain strings (not objects). Each string must be a self-contained, meaningful fact:
- BAD: "REPL" (just a term)
- BAD: "MCP协议" (just a term)
- GOOD: "Claw支持通过MCP协议集成外部工具服务，使用/mcp命令查看已配置的服务器"
- GOOD: "REPL交互模式下支持/compact压缩历史、/session fork分叉会话等命令"

Metadata:
{metadata}

Chunk index:
{chunk_index}

{split_context}Text chunk:
{chunk_text}

Return JSON:
{{
  "chunk_summary": "",
  "key_points": [],
  "business_facts": [],
  "rules_or_policies": [],
  "terms": [],
  "action_items": [],
  "risks": [],
  "open_questions": [],
  "project_memory_candidates": [],
  "lookup_items": [
    {{"key": "", "value": "", "category": "", "source": "", "speed_lookup": "", "content_type": "fact", "retrieval": {{"entities": [], "terms": [], "aliases": [], "keywords": []}}}}
  ],
  "retrieval_hints": {{
    "entities": [],
    "terms": [],
    "aliases": [],
    "keywords": []
  }}
}}"""


def build_document_chunk_chain(llm: BaseChatModel) -> Any:
    prompt = ChatPromptTemplate.from_template(
        DOCUMENT_CHUNK_SYSTEM,
        template_format="f-string",
    )
    parser = JsonOutputParser(pydantic_object=ChunkSummary)
    chain = prompt | llm | parser
    return chain


def run_document_chunk_chain(
    llm: BaseChatModel,
    chunk_text: str,
    chunk_index: int,
    metadata: dict[str, Any],
    split_index: int = 0,
    split_total: int = 0,
) -> tuple[ChunkSummary, dict[str, int]]:
    prompt = ChatPromptTemplate.from_template(
        DOCUMENT_CHUNK_SYSTEM,
        template_format="f-string",
    )
    parser = JsonOutputParser(pydantic_object=ChunkSummary)
    split_context = ""
    if split_index > 0:
        split_context = (
            f"This document is part {split_index} of {split_total} in a split document series.\n"
            f"- Extract information from this part only, do not speculate about other parts.\n"
            f"- All parts of this series will be consolidated into the same memory file.\n"
            f"\n"
        )
    prompt_value: Any = ""
    response: Any = None
    try:
        prompt_value = prompt.invoke(
            {
                "metadata": json.dumps(metadata, ensure_ascii=False),
                "chunk_index": str(chunk_index),
                "chunk_text": chunk_text,
                "split_context": split_context,
            }
        )
        response = llm.invoke(prompt_value)
        token_usage, _ = resolve_token_usage(response, prompt_value)
        result = parser.invoke(response)
        return ChunkSummary.model_validate(_normalize_chunk_payload(result)), token_usage
    except Exception as exc:
        logger.error("Document chunk chain failed (chunk %d): %s", chunk_index, exc)
        token_usage, _ = resolve_token_usage(response, prompt_value) if response is not None else ({}, "")
        if chunk_text.strip():
            return ChunkSummary(
                chunk_summary=f"[LLM error on chunk {chunk_index}]",
                fallback_raw_text=chunk_text.strip(),
            ), token_usage
        return ChunkSummary(chunk_summary=f"[LLM error on chunk {chunk_index}: {exc}]"), token_usage


def _normalize_chunk_payload(result: Any) -> dict[str, Any]:
    payload = dict(result or {}) if isinstance(result, dict) else {}
    for key in (
        "key_points",
        "business_facts",
        "rules_or_policies",
        "terms",
        "action_items",
        "risks",
        "open_questions",
        "project_memory_candidates",
    ):
        value = payload.get(key, [])
        if isinstance(value, list):
            payload[key] = [" ".join(str(item).splitlines()).strip() for item in value if str(item).strip()]
        elif value:
            payload[key] = [" ".join(str(value).splitlines()).strip()]
        else:
            payload[key] = []

    raw_lookup_items = payload.get("lookup_items", [])
    if isinstance(raw_lookup_items, list):
        normalized_items: list[LookupItem] = []
        for raw in raw_lookup_items:
            if isinstance(raw, LookupItem):
                normalized_items.append(raw)
            elif isinstance(raw, dict):
                ct = raw.get("content_type", "fact")
                if ct not in ("problem_solution", "qa", "term_definition", "operation_guide", "configuration", "process", "rule", "fact", "preference"):
                    ct = "fact"
                raw["content_type"] = ct
                retrieval_raw = raw.get("retrieval")
                if isinstance(retrieval_raw, dict):
                    try:
                        raw["retrieval"] = RetrievalHints.model_validate(retrieval_raw)
                    except Exception:
                        raw["retrieval"] = RetrievalHints()
                else:
                    raw["retrieval"] = RetrievalHints()
                try:
                    normalized_items.append(LookupItem(**raw))
                except Exception:
                    pass
        payload["lookup_items"] = normalized_items
    else:
        payload["lookup_items"] = []

    raw_hints = payload.get("retrieval_hints")
    if isinstance(raw_hints, dict):
        try:
            payload["retrieval_hints"] = RetrievalHints.model_validate(raw_hints)
        except Exception:
            payload["retrieval_hints"] = RetrievalHints()
    else:
        payload["retrieval_hints"] = RetrievalHints()
    return payload
