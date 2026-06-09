from __future__ import annotations

import logging
from typing import Any

from langchain_core.language_models import BaseChatModel

from memory_creator.chains.chat_summary_chain import run_chat_summary_chain
from memory_creator.chains.document_chunk_chain import run_document_chunk_chain
from memory_creator.chains.explicit_memory_chain import run_explicit_memory_chain
from memory_creator.promotion.memory_promoter import promote_chat_memory, promote_document_memory, _month_from_metadata
from memory_creator.schemas.chat_summary import ChatSummary
from memory_creator.schemas.document_summary import ChunkSummary, DocumentSummary
from memory_creator.schemas.explicit_memory import ExplicitMemoryResult
from memory_creator.schemas.memory_candidate import MemoryCandidate
from memory_creator.schemas.result import ConsolidationResult
from memory_creator.writers.json_writer import JsonWriter
from app.memory_schema import MemoryItem, RetrievalHints, add_changelog_entry, MEMORY_FILE_PRIORITIES

logger = logging.getLogger(__name__)


def _normalize_metadata(metadata: dict[str, Any] | None) -> dict[str, Any]:
    if metadata is None:
        metadata = {}
    metadata.setdefault("source_id", "")
    metadata.setdefault("title", "")
    metadata.setdefault("created_at", "")
    metadata.setdefault("filename", "")
    metadata.setdefault("mime_type", "")
    metadata.setdefault("extra", {})
    return metadata


def _get_llm(llm: Any | None = None) -> Any:
    if llm is not None:
        return llm
    import os
    if not os.environ.get("OPENAI_API_KEY"):
        raise ValueError("OPENAI_API_KEY not set; cannot initialize default LLM")
    from langchain_openai import ChatOpenAI
    return ChatOpenAI(temperature=0, max_tokens=16384)


def _build_result(
    source_type: str,
    metadata: dict[str, Any],
    candidates: list[MemoryCandidate],
    summary: str,
    memory_dir: str,
    mode: str = "append",
    split_index: int = 0,
    split_total: int = 0,
    token_usage: dict[str, int] | None = None,
) -> ConsolidationResult:
    writer = JsonWriter(memory_dir)
    writer.init_memory_dir()

    updated_files = writer.write_candidates(
        candidates,
        source_type=source_type,
        source_id=str(metadata.get("source_id", "") or ""),
        source_filename=str(metadata.get("title", "") or ""),
        mode=mode,
        split_index=split_index,
        split_total=split_total,
    )

    add_changelog_entry(
        memory_dir,
        action="add",
        target_file=",".join(updated_files),
        item_content_preview=summary[:100] if summary else "",
        reason=f"source_type={source_type}, source_id={metadata.get('source_id', '')}",
    )

    memory_items: dict[str, list[MemoryItem]] = {}
    for c in candidates:
        cat = c.category
        memory_items.setdefault(cat, []).append(c.item)

    return ConsolidationResult(
        source_type=source_type,
        source_id=metadata.get("source_id", ""),
        updated_files=updated_files,
        memory_items=memory_items,
        summary=summary,
        token_usage=dict(token_usage or {}),
    )


def _consolidate_chat(
    llm: BaseChatModel,
    source_text: str,
    metadata: dict[str, Any],
    memory_dir: str,
) -> ConsolidationResult:
    chat_summary, token_usage = run_chat_summary_chain(llm, source_text, metadata)
    candidates: list[MemoryCandidate] = promote_chat_memory(chat_summary, metadata)

    return _build_result(
        source_type="chat",
        metadata=metadata,
        candidates=candidates,
        summary=chat_summary.conversation_summary,
        memory_dir=memory_dir,
        mode="append",
        token_usage=token_usage,
    )


def _consolidate_document(
    llm: BaseChatModel,
    source_text: str,
    metadata: dict[str, Any],
    memory_dir: str,
    mode: str,
) -> ConsolidationResult:
    extra = metadata.get("extra", {})
    split_index = int(extra.get("split_index", 0))
    split_total = int(extra.get("split_total", 0))

    cs, token_usage = run_document_chunk_chain(
        llm,
        source_text,
        0,
        metadata,
        split_index=split_index,
        split_total=split_total,
    )

    doc_summary = DocumentSummary(
        document_summary=cs.chunk_summary,
        key_points=cs.key_points,
        business_facts=cs.business_facts,
        rules_or_policies=cs.rules_or_policies,
        terms=cs.terms,
        action_items=cs.action_items,
        risks=cs.risks,
        open_questions=cs.open_questions,
        project_memory_candidates=cs.project_memory_candidates,
        lookup_items=list(cs.lookup_items) if cs.lookup_items else [],
        fallback_raw_text=cs.fallback_raw_text,
        retrieval_hints=cs.retrieval_hints,
    )

    candidates: list[MemoryCandidate] = promote_document_memory(doc_summary, metadata, split_index, split_total)

    return _build_result(
        source_type="document",
        metadata=metadata,
        candidates=candidates,
        summary=doc_summary.document_summary,
        memory_dir=memory_dir,
        mode=mode,
        split_index=split_index,
        split_total=split_total,
        token_usage=token_usage,
    )


def _consolidate_explicit(
    llm: BaseChatModel,
    source_text: str,
    metadata: dict[str, Any],
    memory_dir: str,
) -> ConsolidationResult:
    result, token_usage = run_explicit_memory_chain(llm, source_text, metadata)
    _validate_explicit_memory_result(result)
    candidates: list[MemoryCandidate] = _promote_explicit_memory(result, metadata)

    return _build_result(
        source_type="explicit",
        metadata=metadata,
        candidates=candidates,
        summary=result.summary,
        memory_dir=memory_dir,
        mode="append",
        token_usage=token_usage,
    )


def _iter_explicit_memory_items(result: ExplicitMemoryResult) -> list[tuple[str, Any]]:
    items: list[tuple[str, Any]] = []
    for category, category_items in (
        ("explicit", result.explicit_memories),
        ("profile", result.profile_candidates),
        ("work", result.work_facts),
        ("timeline", result.timeline_items),
    ):
        items.extend((category, item) for item in category_items)
    return items


def _validate_explicit_memory_result(result: ExplicitMemoryResult) -> None:
    items = _iter_explicit_memory_items(result)
    if not items:
        raise ValueError("显式记忆 Agent 未生成可写入的记忆条目；请检查提示词或模型输出。")

    missing = [
        f"{category}:{str(item.content or '')[:80]}"
        for category, item in items
        if not str(item.speed_lookup or "").strip()
    ]
    if missing:
        preview = "；".join(missing[:3])
        raise ValueError(
            "显式记忆 Agent 未为所有条目生成非空 speed_lookup，已拒绝写入空速查词记忆: "
            + preview
        )


def _promote_explicit_memory(
    result: ExplicitMemoryResult,
    metadata: dict[str, Any],
) -> list[MemoryCandidate]:
    candidates: list[MemoryCandidate] = []
    month = _month_from_metadata(metadata)
    source_id = str(metadata.get("source_id", "") or "")

    for item in result.explicit_memories:
        candidates.append(MemoryCandidate(
            category="explicit",
            item=MemoryItem(
                content=item.content,
                content_type=item.content_type,
                speed_lookup=item.speed_lookup,
                retrieval=item.retrieval if item.retrieval else RetrievalHints(),
                source="explicit",
                source_id=source_id,
                priority=MEMORY_FILE_PRIORITIES["explicit"],
            ),
            confidence=1.0,
            target_file="explicit.json",
        ))

    for item in result.profile_candidates:
        candidates.append(MemoryCandidate(
            category="profile",
            item=MemoryItem(
                content=item.content,
                content_type=item.content_type,
                speed_lookup=item.speed_lookup,
                retrieval=item.retrieval if item.retrieval else RetrievalHints(),
                source="explicit",
                source_id=source_id,
                priority=MEMORY_FILE_PRIORITIES["profile"],
            ),
            confidence=0.9,
            target_file="profile.json",
        ))

    for item in result.work_facts:
        candidates.append(MemoryCandidate(
            category="work",
            item=MemoryItem(
                content=item.content,
                content_type=item.content_type,
                speed_lookup=item.speed_lookup,
                retrieval=item.retrieval if item.retrieval else RetrievalHints(),
                source="explicit",
                source_id=source_id,
                priority=MEMORY_FILE_PRIORITIES["work"],
            ),
            confidence=0.9,
            target_file="work.json",
        ))

    for item in result.timeline_items:
        candidates.append(MemoryCandidate(
            category="timeline",
            item=MemoryItem(
                content=item.content,
                content_type=item.content_type,
                speed_lookup=item.speed_lookup,
                retrieval=item.retrieval if item.retrieval else RetrievalHints(),
                source="explicit",
                source_id=source_id,
                priority=MEMORY_FILE_PRIORITIES["timeline"],
            ),
            confidence=0.9,
            target_file=f"timeline/{month}.json",
        ))

    return candidates


def consolidate_memory_source(
    source_type: str,
    source_text: str,
    metadata: dict[str, Any] | None = None,
    memory_dir: str = ".memory",
    llm: BaseChatModel | None = None,
    mode: str = "append",
) -> ConsolidationResult:
    metadata = _normalize_metadata(metadata)
    model = _get_llm(llm)

    if source_type == "chat":
        return _consolidate_chat(model, source_text, metadata, memory_dir)
    elif source_type == "document":
        return _consolidate_document(model, source_text, metadata, memory_dir, mode)
    elif source_type == "explicit":
        return _consolidate_explicit(model, source_text, metadata, memory_dir)
    else:
        raise ValueError(f"Unsupported source_type: {source_type}")


def consolidate_chat_transcript(
    source_text: str,
    metadata: dict[str, Any] | None = None,
    memory_dir: str = ".memory",
    llm: BaseChatModel | None = None,
) -> ConsolidationResult:
    return consolidate_memory_source("chat", source_text, metadata, memory_dir, llm)


def consolidate_document_text(
    source_text: str,
    metadata: dict[str, Any] | None = None,
    memory_dir: str = ".memory",
    llm: BaseChatModel | None = None,
) -> ConsolidationResult:
    return consolidate_memory_source("document", source_text, metadata, memory_dir, llm)
