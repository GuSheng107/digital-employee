from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.llm_usage import extract_token_usage, resolve_token_usage
from memory_creator.schemas.explicit_memory import ExplicitMemoryResult, ExplicitMemoryItem
from app.memory_schema import RetrievalHints

logger = logging.getLogger(__name__)

EXPLICIT_MEMORY_SYSTEM = """You are the explicit memory consolidation module of memory-creator.

Your task is to refine and categorize raw text that a user explicitly wants to remember.

## CRITICAL RULES (MUST FOLLOW)

1. **NEVER split a single piece of information across multiple items.**
   If the user says "X: Y" or "X, 可能的原因: Y" or "X怎么办: Y", this is ONE item, not two.
   - CORRECT: "问题: 聚水潭推送了入库单到店家但库存没有变动 | 原因: erp设置了不管控库存"
   - WRONG: two separate items "聚水潭推送了入库单到店家但库存没有变动" + "erp设置了不管控库存"
   - CORRECT: "问题: 推送商品提示类目不存在 | 原因1: 授权管理-规格模板需要填服装 | 原因2: 店家选择的类目与聚水潭的类目不对应"
   - WRONG: two items "推送商品提示类目不存在, 授权管理-规格模板需要填服装" + "或者: 店家选择的类目是否与聚水潭的类目相对应"

2. **Each memory item content must be a SINGLE LINE without line breaks.**
   Combine question+answer, problem+cause, term+definition into one line using "|" separator.

3. **Preserve the original meaning exactly.** Do not truncate, summarize, or drop any part.
   If the input says "可能的原因: erp设置了不管控库存", the output MUST include both the problem AND the cause.

4. **NEVER create an item that is just a continuation of a previous item.**
   If an item starts with "或者", "还有", "另外", "原因:", "解决:", it MUST be merged with the previous item.

5. **Every item must be self-contained and independently understandable.**
   An item like "erp设置了不管控库存" without context is useless. It must be combined with its problem.

6. **If a user mentions multiple causes/solutions for one problem, list them in ONE item:**
   "问题: ... | 原因1: ... | 原因2: ..."

7. **User input is always related.** Do not treat different sentences from the same input as independent facts. They share context and should be combined when they describe the same topic.

8. **NEVER keep raw `q:` / `a:` text as the final content.**
   Normalize it into the canonical format:
   - Input: "q: 聚水潭有类目,商品下载到店家类目变成了其他 a: oms-授权管理-仅同步一次类目 是否开启"
   - CORRECT: "问题: 聚水潭有类目,商品下载到店家类目变成了其他 | 答案: oms-授权管理-仅同步一次类目 是否开启"
   - WRONG: "q: 聚水潭有类目,商品下载到店家类目变成了其他 a: oms-授权管理-仅同步一次类目 是否开启"

## Content type format

Identify the type and apply the matching format:
- Problem + cause/solution → "问题: ... | 原因/解决: ..."
- Q&A pair → "问题: ... | 答案: ..."
- Term/definition → "术语: ... | 定义: ..."
- Operation guide → "操作: ... | 步骤: ..."
- Configuration → "配置: ... | 值: ..."
- Process/flow → "流程: ... | 步骤: ..."
- Decision/rule → "规则: ... | 说明: ..."
- General fact → "事实: ..."

## content_type values

For each item, choose the best content_type:
- "problem_solution" — problem + cause/solution
- "qa" — question + answer
- "term_definition" — term + definition
- "operation_guide" — operation steps
- "configuration" — config key + value
- "process" — process/flow steps
- "rule" — decision/rule
- "fact" — general fact (default)
- "preference" — user preference

## speed_lookup rules (VERY IMPORTANT)

For each item, generate a speed_lookup string — a pipe-separated list of useful search keywords.
The `speed_lookup` field is REQUIRED for every item in explicit_memories, profile_candidates, work_facts, and timeline_items.
You MUST fill speed_lookup with meaningful keywords. Empty speed_lookup is invalid.
If you cannot produce speed_lookup for an item, do not output that item; rethink the item until every output item has non-empty speed_lookup.
NEVER return plain string items. Every item MUST be an object with content, content_type, speed_lookup, and retrieval.

You MUST understand Chinese word boundaries. Each keyword must be a semantically complete word or compound, NOT a random substring.

GOOD examples:
- Input: "销发分离是指销售店铺跟发货仓库不是同一个"
  speed_lookup: "销发分离|销售店铺|发货仓库"
- Input: "聚水潭推送了入库单到店家，但是库存没有变动，可能的原因: ERP设置了不管控库存"
  speed_lookup: "入库单|库存|推送|库存不变|不管控库存|ERP设置"
- Input: "采购订单和入库单从聚水潭拉到店家，在哪里拉取? 全局设置-基于采购订单回写"
  speed_lookup: "采购订单|入库单|拉取|聚水潭|全局设置|采购订单回写"
- Input: "q: 聚水潭有类目,商品下载到店家类目变成了其他 a: oms-授权管理-仅同步一次类目 是否开启"
  speed_lookup: "聚水潭|商品下载|店家类目|仅同步一次类目|OMS授权管理"

BAD examples (NEVER do this):
- "销发分离是指|销售店铺跟发|货仓库不是同|一个" ← words broken in the middle!
- "推送了入库|单到店家" ← "入库单" broken into "入库" + "单到店家"
- "采购订单和入库单|从聚水潭拉到店家" ← too long, not a keyword

Rules:
- Each keyword: 2-6 characters for Chinese, any length for English/abbreviations
- Extract nouns, compound nouns, domain terms — the words users would actually search with
- NEVER include: 的,了,是,在,有,可能,原因,或者,如果,需要,可以,什么,怎么,如何,一个,不是,但是
- NEVER include single characters
- Prefer specific terms over generic ones (e.g. "销发分离" not "分离")
- **Sub-term extraction**: When a keyword is a compound noun ending with a company/product suffix (e.g., 科技, 公司, 集团, 平台, 系统), also include the core sub-term as a separate keyword. Example: "店家科技" → include both "店家科技" AND "店家"; "聚水潭ERP" → include "聚水潭"
- **Intent keywords**: Include keywords that reflect the user's search intent, not just literal terms. For company/product info, include "公司介绍|企业介绍|产品体系|简介"; for operation guides, include "操作|步骤|流程"; for problems, include "问题|原因|解决"
- **Abbreviations**: Include common abbreviations or short forms users might search with (e.g., "店+" for "店家", "ERP" for "企业资源计划")

## Categories

IMPORTANT: Distribute items across categories based on their NATURE. Do NOT put everything into explicit_memories.
Each source fact MUST appear in only one category. If two categories would convey the same information, choose exactly one category and omit the duplicate.

- explicit_memories: User/admin configured memory supplied by this explicit-memory task, including Q&A/problem-solution entries that should be remembered directly. A business Q&A from this source should normally become exactly one explicit_memory item, with normalized content and non-empty speed_lookup. Do NOT also copy the same Q&A into work_facts.
- profile_candidates: User preferences, habits, or personal traits (e.g., "我喜欢用Python", "习惯先写测试")
- work_facts: Additional business domain knowledge, system operations, workflows, data relationships, term definitions, problem-solution pairs, or technical facts that are NOT already represented in explicit_memories. Never duplicate an explicit_memory item here.
- timeline_items: Time-bound events or milestones with specific dates

## retrieval per item

For each item, provide a retrieval object:
- entities: Named entities (company, product, system names). Include sub-terms of compound names (e.g., for "店家科技", include both "店家科技" and "店家")
- terms: Domain-specific terms and technical concepts
- aliases: Alternative names, abbreviations, synonyms, short forms. MUST include common abbreviations users might search with (e.g., "店+" for "店家科技", "JST" for "聚水潭")
- keywords: High-frequency search terms. Include intent-related terms users might use when searching for this information (e.g., "公司介绍", "企业介绍", "产品体系" for company info; "操作", "步骤" for guides)
- Keep each list concise (max 5 items per category)
- Do NOT include generic words or stop words

Raw text to remember:
{source_text}

Metadata:
{metadata}

Return JSON:
{{
  "summary": "One-sentence summary of what the user wants to remember",
  "explicit_memories": [
    {{"content": "...", "content_type": "problem_solution", "speed_lookup": "keyword1|keyword2", "retrieval": {{"entities": [], "terms": [], "aliases": [], "keywords": []}}}}
  ],
  "profile_candidates": [
    {{"content": "...", "content_type": "preference", "speed_lookup": "keyword1|keyword2", "retrieval": {{"entities": [], "terms": [], "aliases": [], "keywords": []}}}}
  ],
  "work_facts": [
    {{"content": "...", "content_type": "fact", "speed_lookup": "keyword1|keyword2", "retrieval": {{"entities": [], "terms": [], "aliases": [], "keywords": []}}}}
  ],
  "timeline_items": [
    {{"content": "...", "content_type": "fact", "speed_lookup": "keyword1|keyword2", "retrieval": {{"entities": [], "terms": [], "aliases": [], "keywords": []}}}}
  ]
}}"""


def build_explicit_memory_chain(llm: BaseChatModel) -> Any:
    prompt = ChatPromptTemplate.from_template(
        EXPLICIT_MEMORY_SYSTEM,
        template_format="f-string",
    )
    parser = JsonOutputParser(pydantic_object=ExplicitMemoryResult)
    chain = prompt | llm | parser
    return chain


def _extract_token_usage(message: Any) -> dict[str, int]:
    return extract_token_usage(message)


def run_explicit_memory_chain(
    llm: BaseChatModel,
    source_text: str,
    metadata: dict[str, Any],
) -> tuple[ExplicitMemoryResult, dict[str, int]]:
    prompt = ChatPromptTemplate.from_template(
        EXPLICIT_MEMORY_SYSTEM,
        template_format="f-string",
    )
    parser = JsonOutputParser(pydantic_object=ExplicitMemoryResult)
    prompt_value: Any = ""
    response: Any = None
    try:
        prompt_value = prompt.invoke(
            {
                "source_text": source_text,
                "metadata": json.dumps(metadata, ensure_ascii=False),
            }
        )
        response = llm.invoke(prompt_value)
        token_usage, _ = resolve_token_usage(response, prompt_value)
        result = parser.invoke(response)
        parsed = _normalize_payload(result)
        return _clean_result(parsed), token_usage
    except Exception as exc:
        logger.error("Explicit memory chain failed: %s", exc)
        token_usage, _ = resolve_token_usage(response, prompt_value) if response is not None else ({}, "")
        return ExplicitMemoryResult(summary=f"[LLM error: {exc}]"), token_usage


def _normalize_payload(result: Any) -> ExplicitMemoryResult:
    payload = dict(result or {}) if isinstance(result, dict) else {}
    payload["summary"] = str(payload.get("summary", "") or "").strip()

    for key in ("explicit_memories", "profile_candidates", "work_facts", "timeline_items"):
        raw_list = payload.get(key, [])
        if not isinstance(raw_list, list):
            raw_list = []
        items: list[ExplicitMemoryItem] = []
        for raw in raw_list:
            if isinstance(raw, ExplicitMemoryItem):
                items.append(raw)
            elif isinstance(raw, dict):
                content = " ".join(str(raw.get("content", "")).splitlines()).strip()
                if not content:
                    continue
                raw["content"] = content
                ct = raw.get("content_type", "fact")
                if ct not in ("problem_solution", "qa", "term_definition", "operation_guide", "configuration", "process", "rule", "fact", "preference"):
                    ct = "fact"
                raw["content_type"] = ct
                raw["speed_lookup"] = str(raw.get("speed_lookup", "")).strip()
                retrieval_raw = raw.get("retrieval")
                if isinstance(retrieval_raw, dict):
                    try:
                        raw["retrieval"] = RetrievalHints.model_validate(retrieval_raw)
                    except Exception:
                        raw["retrieval"] = RetrievalHints()
                else:
                    raw["retrieval"] = RetrievalHints()
                items.append(ExplicitMemoryItem(**raw))
            elif isinstance(raw, str):
                content = " ".join(raw.splitlines()).strip()
                if content:
                    items.append(ExplicitMemoryItem(content=content))
        payload[key] = items

    return ExplicitMemoryResult(
        summary=payload["summary"],
        explicit_memories=payload["explicit_memories"],
        profile_candidates=payload["profile_candidates"],
        work_facts=payload["work_facts"],
        timeline_items=payload["timeline_items"],
    )


def _clean_result(result: ExplicitMemoryResult) -> ExplicitMemoryResult:
    for field_name in ("explicit_memories", "profile_candidates", "work_facts", "timeline_items"):
        cleaned_items: list[ExplicitMemoryItem] = []
        for item in getattr(result, field_name):
            cleaned = _clean_speed_lookup(item.speed_lookup)
            if cleaned != item.speed_lookup:
                item = ExplicitMemoryItem(
                    content=item.content,
                    content_type=item.content_type,
                    speed_lookup=cleaned,
                    retrieval=item.retrieval,
                )
            cleaned_items.append(item)
        setattr(result, field_name, cleaned_items)
    return result


def _clean_speed_lookup(lookup: str) -> str:
    if not lookup:
        return lookup
    parts = [p.strip() for p in lookup.split("|") if p.strip()]
    cleaned: list[str] = []
    for p in parts:
        if len(p) <= 1:
            continue
        cleaned.append(p)
    return "|".join(cleaned)


