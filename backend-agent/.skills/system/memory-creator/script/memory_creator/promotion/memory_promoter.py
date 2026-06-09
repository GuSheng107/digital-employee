from __future__ import annotations

from datetime import datetime
from typing import Any

from app.memory_schema import MemoryItem, RetrievalHints, MEMORY_FILE_PRIORITIES
from memory_creator.schemas.chat_summary import ChatSummary
from memory_creator.schemas.document_summary import DocumentSummary
from memory_creator.schemas.memory_candidate import MemoryCandidate


def _now_month() -> str:
    return datetime.now().strftime("%Y-%m")


def _month_from_metadata(metadata: dict[str, Any]) -> str:
    created_at = metadata.get("created_at", "")
    if created_at and len(created_at) >= 7:
        return created_at[:7]
    return _now_month()


def _chat_item_to_memory_item(
    chat_item: Any,
    *,
    source: str = "chat",
    source_id: str = "",
    priority: float = 1.0,
) -> MemoryItem:
    return MemoryItem(
        content=chat_item.content,
        content_type=chat_item.content_type,
        speed_lookup=chat_item.speed_lookup,
        retrieval=chat_item.retrieval if chat_item.retrieval else RetrievalHints(),
        source=source,
        source_id=source_id,
        priority=priority,
    )


def promote_chat_memory(
    summary: ChatSummary,
    metadata: dict[str, Any],
) -> list[MemoryCandidate]:
    candidates: list[MemoryCandidate] = []
    month = _month_from_metadata(metadata)
    source_id = str(metadata.get("source_id", "") or "")

    for item in summary.explicit_memories:
        candidates.append(
            MemoryCandidate(
                category="explicit",
                item=_chat_item_to_memory_item(item, source="chat", source_id=source_id, priority=MEMORY_FILE_PRIORITIES["explicit"]),
                confidence=1.0,
                target_file="explicit.json",
            )
        )

    for item in summary.profile_candidates:
        confidence = 0.7 if any(kw in item.content for kw in ("喜欢", "偏好", "习惯", "prefer", "like", "always")) else 0.8
        candidates.append(
            MemoryCandidate(
                category="profile",
                item=_chat_item_to_memory_item(item, source="chat", source_id=source_id, priority=MEMORY_FILE_PRIORITIES["profile"]),
                confidence=confidence,
                target_file="profile.json",
            )
        )

    for item in summary.business_facts + summary.decisions:
        candidates.append(
            MemoryCandidate(
                category="work",
                item=_chat_item_to_memory_item(item, source="chat", source_id=source_id, priority=MEMORY_FILE_PRIORITIES["work"]),
                confidence=0.9,
                target_file="work.json",
            )
        )

    for item in summary.open_questions:
        candidates.append(
            MemoryCandidate(
                category="inbox",
                item=_chat_item_to_memory_item(item, source="chat", source_id=source_id, priority=MEMORY_FILE_PRIORITIES["inbox"]),
                confidence=0.6,
                target_file="inbox.json",
            )
        )

    for item in summary.inbox_items:
        candidates.append(
            MemoryCandidate(
                category="inbox",
                item=_chat_item_to_memory_item(item, source="chat", source_id=source_id, priority=MEMORY_FILE_PRIORITIES["inbox"]),
                confidence=0.5,
                target_file="inbox.json",
            )
        )

    if summary.conversation_summary:
        candidates.append(
            MemoryCandidate(
                category="timeline",
                item=MemoryItem(
                    content=summary.conversation_summary,
                    content_type="fact",
                    source="chat",
                    source_id=source_id,
                    priority=MEMORY_FILE_PRIORITIES["timeline"],
                ),
                confidence=1.0,
                target_file=f"timeline/{month}.json",
            )
        )

    for item in summary.timeline_items:
        candidates.append(
            MemoryCandidate(
                category="timeline",
                item=_chat_item_to_memory_item(item, source="chat", source_id=source_id, priority=MEMORY_FILE_PRIORITIES["timeline"]),
                confidence=0.9,
                target_file=f"timeline/{month}.json",
            )
        )

    return candidates


def promote_document_memory(
    summary: DocumentSummary,
    metadata: dict[str, Any],
    split_index: int = 0,
    split_total: int = 0,
) -> list[MemoryCandidate]:
    candidates: list[MemoryCandidate] = []
    source_id = metadata.get("source_id", "unknown")
    month = _month_from_metadata(metadata)
    hints = summary.retrieval_hints

    doc_items = (
        [summary.document_summary]
        + summary.key_points
        + summary.business_facts
        + summary.rules_or_policies
        + summary.terms
        + summary.action_items
        + summary.risks
        + summary.open_questions
    )
    for item in doc_items:
        if item:
            candidates.append(
                MemoryCandidate(
                    category="document",
                    item=MemoryItem(
                        content=item,
                        content_type="fact",
                        source="document",
                        source_id=source_id,
                        retrieval=hints.model_copy(),
                        priority=MEMORY_FILE_PRIORITIES["document"],
                    ),
                    confidence=0.9,
                    target_file=f"documents/{source_id}.json",
                )
            )

    for lookup in summary.lookup_items:
        if lookup.key and lookup.value:
            content = f"查询词: {lookup.key} | 答案: {lookup.value}"
            if lookup.category:
                content += f" [{lookup.category}]"
            if lookup.source:
                content += f" | 来源: {lookup.source[:80]}"
        elif lookup.key:
            content = f"查询词: {lookup.key}"
            if lookup.category:
                content += f" [{lookup.category}]"
        else:
            continue
        candidates.append(
            MemoryCandidate(
                category="document",
                item=MemoryItem(
                    content=content,
                    content_type=lookup.content_type,
                    speed_lookup=lookup.speed_lookup,
                    retrieval=lookup.retrieval if lookup.retrieval else RetrievalHints(),
                    source="document",
                    source_id=source_id,
                    priority=MEMORY_FILE_PRIORITIES["document"],
                ),
                confidence=0.9,
                target_file=f"documents/{source_id}.json",
            )
        )

    for item in summary.project_memory_candidates:
        candidates.append(
            MemoryCandidate(
                category="work",
                item=MemoryItem(
                    content=item,
                    content_type="fact",
                    source="document",
                    source_id=source_id,
                    retrieval=hints.model_copy(),
                    priority=MEMORY_FILE_PRIORITIES["work"],
                ),
                confidence=0.8,
                target_file="work.json",
            )
        )

    if summary.fallback_raw_text.strip():
        candidates.append(
            MemoryCandidate(
                category="inbox",
                item=MemoryItem(
                    content=summary.fallback_raw_text.strip(),
                    content_type="fact",
                    source="document",
                    source_id=source_id,
                    retrieval=hints.model_copy(),
                    priority=MEMORY_FILE_PRIORITIES["inbox"],
                ),
                confidence=0.1,
                target_file="inbox.json",
            )
        )

    if summary.document_summary:
        candidates.append(
            MemoryCandidate(
                category="timeline",
                item=MemoryItem(
                    content=summary.document_summary,
                    content_type="fact",
                    source="document",
                    source_id=source_id,
                    retrieval=hints.model_copy(),
                    priority=MEMORY_FILE_PRIORITIES["timeline"],
                ),
                confidence=0.9,
                target_file=f"timeline/{month}.json",
            )
        )

    return candidates
