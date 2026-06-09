from __future__ import annotations

import re
import logging
from typing import Any

from app.memory_schema import MemoryItem

logger = logging.getLogger(__name__)

CONTENT_ONLY_SCORE_CAP = 0.99

_QUERY_STOPWORDS = {
    "帮我",
    "我要",
    "我想",
    "请问",
    "一下",
    "一个",
    "这个",
    "那个",
    "什么",
    "怎么",
    "如何",
    "哪里",
    "在哪",
    "查询",
    "查看",
    "搜索",
    "获取",
    "关于",
    "从",
    "在",
    "的",
}

_INTENT_EXPANSIONS: dict[str, list[str]] = {
    "介绍": ["公司介绍", "企业介绍", "产品介绍", "产品体系", "简介"],
    "描述": ["公司描述", "企业描述", "产品描述", "简介"],
    "说明": ["说明", "介绍", "简介"],
    "做": ["业务", "产品", "服务"],
    "公司": ["企业"],
    "企业": ["公司"],
}

_ENTITY_SUFFIXES = [
    "科技", "公司", "集团", "有限", "技术", "网络",
    "信息", "软件", "服务", "平台", "系统",
]

_BOT_MENTION_WITH_SEPARATOR_RE = re.compile(r"@[^\s,，:：]+(?=[\s,，:：])")
_BOT_SUFFIX_MENTION_RE = re.compile(r"@[^\s,，:：]*(?:机器人|小助手|助手|bot)(?=\S)", re.IGNORECASE)
_BOT_INTENT_BOUNDARIES = (
    "帮我查一下", "帮我查下", "帮我查", "帮忙查一下", "帮忙查下", "帮忙查",
    "查一下", "查下", "帮我", "我要", "我想", "请问", "查询", "查看",
    "搜索", "获取", "介绍一下", "介绍下", "介绍", "描述一下", "描述下", "描述",
    "说明一下", "说明下", "说明", "解释一下", "解释下", "解释", "告诉我",
    "讲讲", "聊聊", "谈谈", "说说", "了解一下", "了解下", "了解", "什么是",
    "什么叫", "怎么", "如何", "为什么", "为何",
)

# 前缀意图词（从查询开头剥离，长词在前确保优先匹配）
_PREFIX_INTENT_RE = re.compile(
    r"^(帮我查一下|帮我查下|帮我查|帮忙查一下|帮忙查下|帮忙查|查一下|查下|查|"
    r"帮我|我要|我想|请问|能不能|可不可以|可否|查询|查看|搜索|获取|从|在|"
    r"介绍一下|介绍下|介绍|描述一下|描述下|描述|说明一下|说明下|说明|"
    r"解释一下|解释下|解释|告诉我|讲讲|聊聊|谈谈|说说|了解一下|了解下|了解|"
    r"什么是|什么叫|怎么|如何|为什么|为何|哪|哪些|哪个)+"
)

# 后缀疑问词（从查询末尾剥离，长词在前）
_SUFFIX_QUESTION_RE = re.compile(
    r"(是做什么的|做什么的|是什么|是啥|是什么意思|有什么|有哪些|"
    r"一下|怎么|如何|吗|呢|的|了|吧|啊|嘛|么|吗|呀|哇|哦|噢)+$"
)

# 中间疑问词（作为分词分隔符）
_MID_QUESTION_WORDS_RE = re.compile(
    r"(是怎么|是怎么做|是做什么|是怎么回|是怎么操|是怎么处|"
    r"怎么|如何|为什么|为何|哪里|在哪|哪个|哪些|什么)"
)


def _strip_query_affixes(value: str) -> str:
    text = value.strip()
    while text:
        previous = text
        text = _PREFIX_INTENT_RE.sub("", text)
        text = _SUFFIX_QUESTION_RE.sub("", text)
        text = text.strip()
        if text == previous:
            break
    return text


def _strip_bot_mentions(value: str) -> str:
    text = value.strip()
    if not text:
        return text
    text = _BOT_MENTION_WITH_SEPARATOR_RE.sub(" ", text)
    text = _BOT_SUFFIX_MENTION_RE.sub(" ", text)
    if text.startswith("@"):
        positions = [
            idx for marker in _BOT_INTENT_BOUNDARIES
            if (idx := text.find(marker, 1)) > 0
        ]
        if positions:
            text = text[min(positions):]
    return text.strip()


def _append_query_term(terms: list[str], seen: set[str], term: str) -> None:
    clean = term.strip()
    if len(clean) <= 1 or clean in _QUERY_STOPWORDS or clean in seen:
        return
    seen.add(clean)
    terms.append(clean)


def _append_term_variants(terms: list[str], seen: set[str], term: str) -> None:
    _append_query_term(terms, seen, term)

    # "店+产品体系" should still match both the company alias and intent term.
    if "+" in term:
        before, after = term.split("+", 1)
        if before:
            _append_query_term(terms, seen, f"{before}+")
        if after:
            _append_query_term(terms, seen, after)

    # "销发分离的配置" should still expose the entity and the intent.
    for part in re.split(r"(?:的|关于)", term):
        _append_query_term(terms, seen, part)

    # "推送商品到店家" / "采购订单和入库单" should expose both sides.
    for part in re.split(r"(?:到|从|和|及|与)", term):
        _append_query_term(terms, seen, part)

    # Sub-term extraction: strip entity suffixes.
    for suffix in _ENTITY_SUFFIXES:
        if term.endswith(suffix) and len(term) > len(suffix) + 1:
            _append_query_term(terms, seen, term[: -len(suffix)])


def extract_query_terms(query: str, include_intent_expansions: bool = True) -> list[str]:
    # Step 1: 对整句做 bot mention 与前缀/后缀清理
    cleaned = _strip_bot_mentions(query.lower())
    cleaned = _strip_query_affixes(cleaned)

    # Step 2: 按中间疑问词分割（如 "聚水潭怎么推送商品" → "聚水潭" + "推送商品"）
    mid_parts = _MID_QUESTION_WORDS_RE.split(cleaned)
    mid_parts = [p.strip() for p in mid_parts if p.strip() and p.strip() not in _QUERY_STOPWORDS]

    # Step 3: 对每个部分按标点/空格分词
    terms: list[str] = []
    seen: set[str] = set()
    for part in mid_parts:
        raw_terms = re.split(r"[\s,，|｜、/\\:：?？!！。.;；()\[\]{}<>《》\"'`]+", part)
        for raw in raw_terms:
            term = _strip_query_affixes(raw.strip())
            if not term:
                continue
            _append_term_variants(terms, seen, term)

    # Step 4: 如果分词后没有有效词（中文无空格），尝试从清理后的整句提取
    if not terms and cleaned and len(cleaned) >= 2:
        _append_term_variants(terms, seen, cleaned)

    # Step 5: 意图词扩展（从原始查询检测）
    if include_intent_expansions:
        query_lower = query.lower()
        for verb, expansions in _INTENT_EXPANSIONS.items():
            if verb in query_lower:
                for exp in expansions:
                    if exp not in seen:
                        seen.add(exp)
                        terms.append(exp)

    return terms


def _iter_item_terms(item: MemoryItem) -> list[str]:
    values: list[str] = []
    if item.speed_lookup:
        values.extend(re.split(r"[|｜,，\s]+", item.speed_lookup.lower()))
    retrieval = item.retrieval
    for field in (retrieval.aliases, retrieval.entities, retrieval.terms, retrieval.keywords):
        values.extend(str(t).lower() for t in field if str(t).strip())
    if item.content:
        values.append(item.content.lower())
    return [value for value in values if value]


def count_query_term_matches(item: MemoryItem, query: str) -> int:
    query_terms = extract_query_terms(query)
    if not query_terms:
        return 0
    item_terms = _iter_item_terms(item)
    matched = 0
    for qt in query_terms:
        if any(qt == it or qt in it or it in qt for it in item_terms):
            matched += 1
    return matched


def score_memory_items(
    items: list[MemoryItem],
    query: str,
    file_weight: float = 1.0,
    extra_query_terms: list[str] | None = None,
) -> list[tuple[MemoryItem, float]]:
    scored: list[tuple[MemoryItem, float]] = []
    query_lower = query.lower()
    query_terms = set(extract_query_terms(query_lower))
    base_query_terms = set(extract_query_terms(query_lower, include_intent_expansions=False))

    # 合并 LLM 扩展词（权重低于原始查询词）
    expanded_terms_set: set[str] = set()
    if extra_query_terms:
        for t in extra_query_terms:
            t_lower = t.lower().strip()
            if t_lower and len(t_lower) > 1:
                expanded_terms_set.add(t_lower)

    normalized_query = _strip_query_affixes(_strip_bot_mentions(query_lower))
    query_chars = set(normalized_query) - {' ', ',', '，', '?', '？', '!', '！', '。', '.'}

    for item in items:
        score = 0.0
        matched_query_terms: set[str] = set()
        has_speed_lookup_match = False
        has_retrieval_match = False

        # --- Tier 1: speed_lookup (highest) ---
        if item.speed_lookup:
            lookup_terms = set(re.split(r'[|｜,，\s]+', item.speed_lookup.lower())) - {''}
            for qt in query_terms:
                matched_this_term = False
                for lt in lookup_terms:
                    if qt == lt:
                        score += 10.0
                        matched_this_term = True
                    elif qt in lt or lt in qt:
                        score += 5.0
                        matched_this_term = True
                if matched_this_term:
                    matched_query_terms.add(qt)
                    has_speed_lookup_match = True

        # --- Tier 2: retrieval hints (secondary) ---
        retrieval = item.retrieval
        all_retrieval_terms: set[str] = set()
        for field in (retrieval.aliases, retrieval.entities, retrieval.terms, retrieval.keywords):
            for t in field:
                all_retrieval_terms.add(t.lower())
        for qt in query_terms:
            matched_this_term = False
            for rt in all_retrieval_terms:
                if qt == rt:
                    score += 5.0
                    matched_this_term = True
                elif qt in rt or rt in qt:
                    score += 2.0
                    matched_this_term = True
            if matched_this_term:
                matched_query_terms.add(qt)
                has_retrieval_match = True

        # --- Tier 2.5: LLM expanded terms (between retrieval and content) ---
        if expanded_terms_set:
            for et in expanded_terms_set:
                matched_lookup = False
                matched_retrieval = False
                # Match against speed_lookup
                if item.speed_lookup:
                    lookup_terms = set(re.split(r'[|｜,，\s]+', item.speed_lookup.lower())) - {''}
                    for lt in lookup_terms:
                        if et == lt:
                            score += 3.0
                            matched_lookup = True
                        elif et in lt or lt in et:
                            score += 1.5
                            matched_lookup = True
                # Match against retrieval
                for rt in all_retrieval_terms:
                    if et == rt:
                        score += 3.0
                        matched_retrieval = True
                    elif et in rt or rt in et:
                        score += 1.5
                        matched_retrieval = True
                if matched_lookup:
                    has_speed_lookup_match = True
                if matched_retrieval:
                    has_retrieval_match = True

        # --- Tier 3: content (supplement only, low weight) ---
        content_lower = item.content.lower()
        for qt in query_terms:
            if qt in content_lower:
                score += 0.5
                matched_query_terms.add(qt)

        structured_match = has_speed_lookup_match or has_retrieval_match

        # Content-only penalty: no speed_lookup or retrieval hit, so it can surface in
        # diagnostics but cannot pass the reader selection threshold by file priority.
        if not structured_match:
            score *= 0.2

        # Char overlap bonus only when speed_lookup or retrieval matched
        if structured_match:
            if query_chars and matched_query_terms:
                content_chars = set(content_lower)
                overlap = len(query_chars & content_chars)
                char_ratio = overlap / len(query_chars) if query_chars else 0
                if char_ratio > 0.5:
                    score += min(char_ratio, 1.0)

        if len(base_query_terms) >= 3 and len(matched_query_terms & base_query_terms) < 2:
            score = 0.0

        if score > 0 and structured_match:
            score += item.priority * 0.1

        if structured_match:
            score *= file_weight
        elif score > 0:
            score = min(score, CONTENT_ONLY_SCORE_CAP)

        scored.append((item, score))

    scored.sort(key=lambda x: x[1], reverse=True)
    return scored
