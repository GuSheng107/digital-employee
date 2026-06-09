from __future__ import annotations

import logging
import re
from typing import Any

from app.memory_schema import MEMORY_FILE_LABELS, MEMORY_FILE_PRIORITIES, MemoryItem, load_document_memory
from memory_reader.loaders.json_loader import JsonLoader
from memory_reader.schemas.memory_output import MemoryOutput
from memory_reader.selection.json_scorer import score_memory_items

logger = logging.getLogger(__name__)

FILE_WEIGHT_MAP: dict[str, float] = {
    "explicit": MEMORY_FILE_PRIORITIES.get("explicit", 10.0),
    "work": MEMORY_FILE_PRIORITIES.get("work", 8.0),
    "profile": MEMORY_FILE_PRIORITIES.get("profile", 6.0),
    "rules": MEMORY_FILE_PRIORITIES.get("rules", 3.0),
    "inbox": MEMORY_FILE_PRIORITIES.get("inbox", 2.0),
    "changelog": MEMORY_FILE_PRIORITIES.get("changelog", 1.0),
}

TOKEN_BUDGET_MODES: dict[str, dict[str, int]] = {
    "compact": {"total": 1500, "rules": 60, "explicit": 300, "work": 360, "profile": 150, "timeline": 120, "document": 360, "inbox": 150},
    "default": {"total": 4000, "rules": 120, "explicit": 720, "work": 960, "profile": 320, "timeline": 400, "document": 1200, "inbox": 280},
    "expanded": {"total": 8000, "rules": 200, "explicit": 960, "work": 1600, "profile": 560, "timeline": 800, "document": 3200, "inbox": 680},
}

SCORE_THRESHOLD = 1.0


def _file_weight_for_key(file_key: str) -> float:
    if file_key in FILE_WEIGHT_MAP:
        return FILE_WEIGHT_MAP[file_key]
    if file_key.startswith("documents/"):
        return MEMORY_FILE_PRIORITIES.get("document", 5.0)
    if file_key.startswith("timeline/"):
        return MEMORY_FILE_PRIORITIES.get("timeline", 4.0)
    return 1.0


def _file_budget_for_key(file_key: str, mode: str, total_budget: int = 0) -> int:
    budgets = TOKEN_BUDGET_MODES.get(mode, TOKEN_BUDGET_MODES["default"])
    # 如果传入了 total_budget 且不在预设 mode 中，按 default 模式等比缩放
    if total_budget and total_budget != budgets.get("total", 0):
        base = TOKEN_BUDGET_MODES["default"]
        ratio = total_budget / base["total"]
        if file_key in base:
            return int(base[file_key] * ratio)
        if file_key.startswith("timeline/"):
            return int(base.get("timeline", 400) * ratio)
        if file_key.startswith("documents/"):
            return int(base.get("document", 1200) * ratio)
        return total_budget
    if file_key in budgets:
        return budgets[file_key]
    if file_key.startswith("timeline/"):
        return budgets.get("timeline", TOKEN_BUDGET_MODES["default"]["timeline"])
    if file_key.startswith("documents/"):
        return budgets.get("document", TOKEN_BUDGET_MODES["default"]["document"])
    return budgets.get("total", TOKEN_BUDGET_MODES["default"]["total"])


def _estimate_tokens(text: str) -> int:
    chinese_chars = len(re.findall(r"[\u4e00-\u9fff]", text))
    other_chars = len(text) - chinese_chars
    return int(chinese_chars * 1.5) + other_chars // 4 + 1


def _dedupe_key(text: str) -> str:
    return re.sub(r"[\s,，。.!！?？:：;；|｜/\\()\[\]{}<>《》\"'`]+", "", text.lower())


def _label_for_file_key(file_key: str, document_labels: dict[str, str] | None = None) -> str:
    if file_key in {"explicit", "manual"}:
        return "管理员配置内容"
    if file_key.startswith("documents/"):
        return "文档记忆"
    return "会话记忆"


def _document_label_for_source(
    source_id: str,
    *,
    memory_root: str,
    document_labels: dict[str, str] | None = None,
) -> str:
    labels = document_labels or {}
    label = str(labels.get(source_id, "") or "").strip()
    if label:
        return label
    dm = load_document_memory(memory_root, source_id)
    label = str(dm.source_filename or "").strip()
    return label


def _source_note_for_item(
    file_key: str,
    item: MemoryItem,
    *,
    memory_root: str,
    document_labels: dict[str, str] | None = None,
) -> str:
    source = str(item.source or "").strip()
    if file_key in {"explicit", "manual"} or source in {"explicit", "manual"}:
        return "来源：管理员配置内容"

    source_id = str(item.source_id or "").strip()
    doc_source_id = ""
    if file_key.startswith("documents/"):
        doc_source_id = file_key.split("/", 1)[1]
    elif source == "document" and source_id:
        doc_source_id = source_id

    if doc_source_id:
        label = _document_label_for_source(
            doc_source_id,
            memory_root=memory_root,
            document_labels=document_labels,
        )
        if label:
            return f"来源：文档《{label}》"
        return "来源：文档记忆"

    return ""


def _confidence_from_selection(selected_count: int, all_file_count: int, used_tokens: int, token_budget: int) -> str:
    if selected_count <= 0:
        return "low"
    if used_tokens >= max(1, token_budget) * 0.95:
        return "medium"
    if all_file_count and selected_count < all_file_count:
        return "high"
    return "medium"


def build_memory_pack(
    query: str,
    memory_root: str = ".memory",
    token_budget: int = 0,
    token_budget_expanded: int = 0,
    llm: Any = None,
    mode: str = "default",
    document_labels: dict[str, str] | None = None,
    expanded_terms: str = "",
) -> MemoryOutput:
    loader = JsonLoader(memory_root)
    all_files = loader.load_all_files()

    # 解析 LLM 扩展词
    extra_terms: list[str] = []
    if expanded_terms:
        import re as _re
        extra_terms = [t.strip() for t in _re.split(r"[|｜,，\s]+", expanded_terms) if t.strip() and len(t.strip()) > 1]

    file_scored: dict[str, list[tuple[MemoryItem, float]]] = {}
    for file_key, mf in all_files.items():
        file_weight = _file_weight_for_key(file_key)
        scored = score_memory_items(mf.items, query, file_weight=file_weight, extra_query_terms=extra_terms)
        filtered = [(item, score) for item, score in scored if score >= SCORE_THRESHOLD]
        if filtered:
            file_scored[file_key] = filtered

    selected: list[tuple[str, MemoryItem, float]] = []
    seen_contents: set[str] = set()
    used_tokens = 0
    budget_omitted_count = 0
    oversized_item_count = 0
    total_budget = int(token_budget or TOKEN_BUDGET_MODES.get(mode, TOKEN_BUDGET_MODES["default"])["total"])
    expanded_total = int(token_budget_expanded) if token_budget_expanded > 0 else total_budget

    file_order = [
        "explicit",
        "work",
        "profile",
        "rules",
        "timeline",
        "documents",
        "inbox",
        "changelog",
    ]

    ordered_files = []
    for fk in file_order:
        for file_key in file_scored:
            if file_key == fk or (fk == "timeline" and file_key.startswith("timeline/")) or (fk == "documents" and file_key.startswith("documents/")):
                if file_key not in ordered_files:
                    ordered_files.append(file_key)
    for file_key in file_scored:
        if file_key not in ordered_files:
            ordered_files.append(file_key)

    # 第一轮：用 base budget 选取
    doc_items_omitted_by_budget = False
    for file_key in ordered_files:
        scored = file_scored[file_key]
        scored.sort(key=lambda x: x[1], reverse=True)

        file_budget = _file_budget_for_key(file_key, mode, total_budget)
        file_used = 0

        for item_index, (item, score) in enumerate(scored):
            item_tokens = _estimate_tokens(item.content)
            if used_tokens + item_tokens > total_budget:
                remaining_in_file = len(scored) - item_index
                budget_omitted_count += remaining_in_file
                if file_key.startswith("documents/"):
                    doc_items_omitted_by_budget = True
                break
            if file_used + item_tokens > file_budget:
                budget_omitted_count += 1
                if item_tokens > file_budget:
                    oversized_item_count += 1
                if file_key.startswith("documents/"):
                    doc_items_omitted_by_budget = True
                continue
            dedupe_key = _dedupe_key(item.content)
            if dedupe_key and dedupe_key in seen_contents:
                continue
            selected.append((file_key, item, score))
            if dedupe_key:
                seen_contents.add(dedupe_key)
            used_tokens += item_tokens
            file_used += item_tokens

    # 第二轮：如果文档命中且有 item 因 budget 被截断，扩展到 expanded budget 重新选取
    if doc_items_omitted_by_budget and expanded_total > total_budget:
        selected = []
        seen_contents = set()
        used_tokens = 0
        budget_omitted_count = 0
        oversized_item_count = 0
        total_budget = expanded_total

        for file_key in ordered_files:
            scored = file_scored[file_key]
            scored.sort(key=lambda x: x[1], reverse=True)

            file_budget = _file_budget_for_key(file_key, mode, total_budget)
            file_used = 0

            for item_index, (item, score) in enumerate(scored):
                item_tokens = _estimate_tokens(item.content)
                if used_tokens + item_tokens > total_budget:
                    remaining_in_file = len(scored) - item_index
                    budget_omitted_count += remaining_in_file
                    break
                if file_used + item_tokens > file_budget:
                    budget_omitted_count += 1
                    if item_tokens > file_budget:
                        oversized_item_count += 1
                    continue
                dedupe_key = _dedupe_key(item.content)
                if dedupe_key and dedupe_key in seen_contents:
                    continue
                selected.append((file_key, item, score))
                if dedupe_key:
                    seen_contents.add(dedupe_key)
                used_tokens += item_tokens
                file_used += item_tokens

    file_stats: dict[str, int] = {}
    for file_key, _item, _score in selected:
        file_stats[file_key] = file_stats.get(file_key, 0) + 1

    selected_files = list(file_stats.keys())
    all_file_keys = list(all_files.keys())
    omitted_files = [fk for fk in all_file_keys if fk not in file_stats]
    no_match_file_count = sum(1 for fk in all_file_keys if fk not in file_scored)

    selected_items = [item for _file_key, item, _score in selected]
    memory_pack = _format_memory_pack(
        selected,
        file_stats,
        memory_root=memory_root,
        document_labels=document_labels,
    )
    confidence = _confidence_from_selection(
        len(selected_items),
        sum(len(mf.items) for mf in all_files.values()),
        used_tokens,
        total_budget,
    )
    if selected_items:
        reason = f"从 {len(selected_files)} 个记忆文件中选中 {len(selected_items)} 条相关条目"
        if no_match_file_count:
            reason += f"；跳过 {no_match_file_count} 个无匹配的文件"
        if used_tokens >= total_budget * 0.95:
            reason += "；已达到 token 预算上限"
        if budget_omitted_count:
            reason += f"；有 {budget_omitted_count} 条相关记忆因预算限制未纳入"
            if oversized_item_count:
                reason += f"（其中 {oversized_item_count} 条单条超过分区预算）"
    else:
        if budget_omitted_count:
            reason = f"当前查询匹配到相关记忆，但有 {budget_omitted_count} 条因预算限制未纳入"
            if oversized_item_count:
                reason += f"（其中 {oversized_item_count} 条单条超过分区预算）"
        else:
            reason = "当前查询未匹配到任何记忆条目"

    return MemoryOutput(
        items=selected_items,
        total_tokens=used_tokens,
        query=query,
        file_stats=file_stats,
        memory_pack=memory_pack,
        selected_files=selected_files,
        selected_sections=selected_files,
        omitted_files=omitted_files,
        token_budget_used_estimate=used_tokens,
        confidence=confidence,
        needs_more_memory=bool(budget_omitted_count),
        reason=reason,
    )


def _format_memory_pack(
    selected: list[tuple[str, MemoryItem, float]],
    file_stats: dict[str, int],
    *,
    memory_root: str,
    document_labels: dict[str, str] | None = None,
) -> str:
    if not selected:
        return ""

    lines: list[str] = []
    current_file = ""
    for file_key, item, _score in selected:
        if file_key != current_file:
            if current_file:
                lines.append("")
            current_file = file_key
            lines.append(f"[{_label_for_file_key(file_key, document_labels=document_labels)}]")

        content = item.content
        if item.speed_lookup:
            content = f"{content} (关键词: {item.speed_lookup})"
        source_note = _source_note_for_item(
            file_key,
            item,
            memory_root=memory_root,
            document_labels=document_labels,
        )
        if source_note:
            content = f"{content} ({source_note})"
        lines.append(f"- {content}")

    header = f"共检索到 {len(selected)} 条相关记忆 (来自 {len(file_stats)} 个文件)"
    return header + "\n" + "\n".join(lines)


def read_memory_for_task(
    current_message: str,
    metadata: dict[str, Any] | None = None,
    llm: Any = None,
) -> dict[str, Any]:
    if metadata is None:
        metadata = {}
    memory_root = metadata.get("memory_root", ".memory")
    token_budget = metadata.get("token_budget", 0)
    token_budget_expanded = metadata.get("token_budget_expanded", 0)
    mode = metadata.get("mode", "default")
    document_labels = metadata.get("document_labels", {})
    expanded_terms = metadata.get("expanded_terms", "")
    if not isinstance(document_labels, dict):
        document_labels = {}
    if not token_budget:
        token_budget = TOKEN_BUDGET_MODES.get(mode, TOKEN_BUDGET_MODES["default"])["total"]
    output = build_memory_pack(
        query=current_message,
        memory_root=memory_root,
        token_budget=token_budget,
        token_budget_expanded=token_budget_expanded,
        llm=llm,
        mode=mode,
        document_labels={str(k): str(v) for k, v in document_labels.items()},
        expanded_terms=expanded_terms,
    )
    return output.model_dump()
