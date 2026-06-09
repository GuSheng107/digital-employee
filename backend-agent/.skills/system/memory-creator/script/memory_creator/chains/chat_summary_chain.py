from __future__ import annotations

import json
import logging
from typing import Any

from langchain_core.language_models import BaseChatModel
from langchain_core.output_parsers import JsonOutputParser
from langchain_core.prompts import ChatPromptTemplate

from app.llm_usage import extract_token_usage, resolve_token_usage
from memory_creator.schemas.chat_summary import ChatSummary, ChatMemoryItem
from app.memory_schema import RetrievalHints

logger = logging.getLogger(__name__)


def _extract_token_usage(message: Any) -> dict[str, int]:
    return extract_token_usage(message)


CHAT_SUMMARY_SYSTEM = """You are the chat memory consolidation module.

Extract reusable long-term memory from a chat transcript.

## CRITICAL RULES

1. Automatic AI reply Q&A pairs must not create memory unless the answer is explicitly marked with user feedback "useful" (for example answer_feedback_result=useful or "用户反馈: useful"). If an AI answer has no feedback or has "useless" feedback, ignore that whole Q&A pair completely.
2. Valuable answers normally come from human/manual replies, AI draft replies that were sent by a human, or AI replies explicitly marked useful by the user. Treat useful-feedback AI replies as high-priority human-confirmed extraction evidence.
3. Only user-confirmed messages can create explicit memory. Bot messages provide context only unless the bot answer was explicitly marked useful by the user.
4. Do not save temporary instructions or low-value small talk.
5. Each memory item content must be a SINGLE LINE without line breaks.
6. **COMBINE ASSOCIATED CONTENT**: When a user states a problem/question and then provides or receives a human-confirmed cause/solution/answer, they MUST be merged into ONE single item.
   - BAD (split): ["采购退货单从聚水潭拉到店家在哪里拉取?", "授权管理-聚水潭里的下载采购退货单"]
   - GOOD (merged): "问题: 采购退货单从聚水潭拉到店家在哪里拉取? | 答案: 授权管理-聚水潭里的下载采购退货单"
   - BAD (split): ["聚水潭推送了入库单到店家，但是库存没有变动，可能的原因:", "erp设置了不管控库存"]
   - GOOD (merged): "问题: 聚水潭推送了入库单到店家，但是库存没有变动 | 原因: erp设置了不管控库存"
   - BAD (split): ["从点击推送商品如果提示类目不存在,可能的原因: 授权管理-规格模板需要填服装", "或者: 店家选择的类目是否与聚水潭的类目相对应"]
   - GOOD (merged): "问题: 推送商品提示类目不存在 | 原因1: 授权管理-规格模板需要填服装 | 原因2: 店家选择的类目与聚水潭的类目不对应"
7. **NEVER split a single fact across multiple items.** A question and its answer/cause/solution are ONE fact. A problem with multiple causes is ONE item.
8. If a user mentions multiple causes/solutions for one problem, list them in ONE item: "问题: ... | 原因1: ... | 原因2: ..."
9. **NEVER create an item that is just a continuation of a previous item.** If an item starts with "或者", "还有", "另外", "原因:", "解决:", it MUST be merged with the previous item, not created as a separate item.
10. **Every item must be self-contained and independently understandable.** An item like "erp设置了不管控库存" without context is useless. It must be combined with its problem: "问题: ... | 原因: erp设置了不管控库存"

## Content format

- Problem + cause/solution → "问题: ... | 原因/解决: ..."
- Q&A pair → "问题: ... | 答案: ..."
- Term/definition → "术语: ... | 定义: ..."
- Operation guide → "操作: ... | 步骤: ..."
- Configuration → "配置: ... | 值: ..."
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

## speed_lookup rules (per item)

Generate a pipe-separated list of 3-8 search keywords for each item.
You MUST understand Chinese word boundaries. Each keyword must be a semantically complete word.

GOOD: "销发分离|销售店铺|发货仓库"
BAD:  "销发分离是指|销售店铺跟发|货仓库不是同"

Rules:
- Each keyword: 2-6 characters for Chinese, any length for English
- Extract nouns, compound nouns, domain terms
- NEVER include: 的,了,是,在,有,可能,原因,或者,如果,需要,可以,什么,怎么,如何,一个,不是,但是
- NEVER include single characters
- **Sub-term extraction**: When a keyword is a compound noun ending with a company/product suffix (e.g., 科技, 公司, 集团, 平台, 系统), also include the core sub-term as a separate keyword. Example: "店家科技" → include both "店家科技" AND "店家"; "聚水潭ERP" → include "聚水潭"
- **Intent keywords**: Include keywords that reflect the user's search intent, not just literal terms. For company/product info, include "公司介绍|企业介绍|产品体系|简介"; for operation guides, include "操作|步骤|流程"; for problems, include "问题|原因|解决"
- **Abbreviations**: Include common abbreviations or short forms users might search with (e.g., "店+" for "店家", "ERP" for "企业资源计划")

## Categories

IMPORTANT: Distribute items across categories based on their NATURE, not just importance. Do NOT put everything into explicit_memories.

- explicit_memories: ONLY things the user explicitly asked to remember (e.g., "记住XXX", "以后都这样", "这是规则"). Direct commands from user to memorize something. Most items should NOT go here.
- profile_candidates: User preferences, habits, personal traits, working style (e.g., "我喜欢用Python", "习惯先写测试", "偏好简洁风格")
- business_facts: Domain knowledge, system operations, workflows, data relationships discovered in conversation (e.g., "聚水潭入库单在全局设置中拉取", "销发分离是指销售店铺和发货仓库不同"). This is the PRIMARY category for work-related Q&A and problem-solution pairs.
- decisions: Conclusions, choices, or agreements made during the conversation (e.g., "决定使用方案A", "统一用REST API")
- open_questions: Questions raised but not yet answered
- inbox_items: Incomplete information needing follow-up
- timeline_items: Time-bound events or milestones

## retrieval per item

For each item, provide a retrieval object:
- entities: Named entities (company, product, system names). Include sub-terms of compound names (e.g., for "店家科技", include both "店家科技" and "店家")
- terms: Domain-specific terms and concepts
- aliases: Alternative names, abbreviations, synonyms, short forms. MUST include common abbreviations users might search with (e.g., "店+" for "店家科技", "JST" for "聚水潭")
- keywords: High-frequency search terms. Include intent-related terms users might use when searching for this information (e.g., "公司介绍", "企业介绍", "产品体系" for company info; "操作", "步骤" for guides)
- Max 5 items per category, no generic words

Metadata:
{metadata}

Chat transcript:
{source_text}

Return JSON:
{{
  "conversation_summary": "",
  "explicit_memories": [
    {{"content": "...", "content_type": "fact", "speed_lookup": "a|b|c", "retrieval": {{"entities": [], "terms": [], "aliases": [], "keywords": []}}}}
  ],
  "profile_candidates": [
    {{"content": "...", "content_type": "preference", "speed_lookup": "a|b|c", "retrieval": {{"entities": [], "terms": [], "aliases": [], "keywords": []}}}}
  ],
  "business_facts": [
    {{"content": "...", "content_type": "fact", "speed_lookup": "a|b|c", "retrieval": {{"entities": [], "terms": [], "aliases": [], "keywords": []}}}}
  ],
  "decisions": [
    {{"content": "...", "content_type": "rule", "speed_lookup": "a|b|c", "retrieval": {{"entities": [], "terms": [], "aliases": [], "keywords": []}}}}
  ],
  "open_questions": [
    {{"content": "...", "content_type": "fact", "speed_lookup": "a|b|c", "retrieval": {{"entities": [], "terms": [], "aliases": [], "keywords": []}}}}
  ],
  "timeline_items": [
    {{"content": "...", "content_type": "fact", "speed_lookup": "a|b|c", "retrieval": {{"entities": [], "terms": [], "aliases": [], "keywords": []}}}}
  ],
  "inbox_items": [
    {{"content": "...", "content_type": "fact", "speed_lookup": "a|b|c", "retrieval": {{"entities": [], "terms": [], "aliases": [], "keywords": []}}}}
  ]
}}"""


def build_chat_summary_chain(llm: BaseChatModel) -> Any:
    prompt = ChatPromptTemplate.from_template(
        CHAT_SUMMARY_SYSTEM,
        template_format="f-string",
    )
    parser = JsonOutputParser(pydantic_object=ChatSummary)
    chain = prompt | llm | parser
    return chain


def run_chat_summary_chain(
    llm: BaseChatModel,
    source_text: str,
    metadata: dict[str, Any],
) -> tuple[ChatSummary, dict[str, int]]:
    prompt = ChatPromptTemplate.from_template(
        CHAT_SUMMARY_SYSTEM,
        template_format="f-string",
    )
    parser = JsonOutputParser(pydantic_object=ChatSummary)
    prompt_value: Any = ""
    response: Any = None
    try:
        prompt_value = prompt.invoke(
            {
                "metadata": json.dumps(metadata, ensure_ascii=False),
                "source_text": source_text,
            }
        )
        response = llm.invoke(prompt_value)
        token_usage, _ = resolve_token_usage(response, prompt_value)
        result = parser.invoke(response)
        return ChatSummary.model_validate(_normalize_chat_summary_payload(result)), token_usage
    except Exception as exc:
        logger.error("Chat summary chain failed: %s", exc)
        token_usage, _ = resolve_token_usage(response, prompt_value) if response is not None else ({}, "")
        return ChatSummary(), token_usage


def _normalize_chat_summary_payload(result: Any) -> dict[str, Any]:
    payload = dict(result or {}) if isinstance(result, dict) else {}
    payload["conversation_summary"] = str(payload.get("conversation_summary", "") or "").strip()

    for key in (
        "explicit_memories",
        "profile_candidates",
        "business_facts",
        "decisions",
        "open_questions",
        "timeline_items",
        "inbox_items",
    ):
        raw_list = payload.get(key, [])
        if not isinstance(raw_list, list):
            raw_list = []
        items: list[ChatMemoryItem] = []
        for raw in raw_list:
            if isinstance(raw, ChatMemoryItem):
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
                items.append(ChatMemoryItem(**raw))
            elif isinstance(raw, str):
                content = " ".join(raw.splitlines()).strip()
                if content:
                    items.append(ChatMemoryItem(content=content))
        payload[key] = items

    return payload
