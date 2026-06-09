"""Runtime query index — temporary session-level instruction storage.

Stores strong-constraint user instructions per chat session.
These are NOT written to long-term .memory/*.json files.

Storage path: .memory/.runtime/session_queries/{chat_id}.json
"""
from __future__ import annotations

import json
import re
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.memory_schema import MemoryItem, RetrievalHints


_MAX_ENTRIES = 50


class RuntimeQueryEntry(BaseModel):
    """A single runtime query instruction."""
    text: str
    created_at: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class RuntimeQueryIndex(BaseModel):
    """Runtime query index for a single chat session."""
    chat_id: str
    entries: list[RuntimeQueryEntry] = Field(default_factory=list)


# Strong-constraint instruction patterns
_CONSTRAINT_PREFIXES = [
    r"以后默认",
    r"不要",
    r"必须",
    r"记住",
    r"不要改",
    r"纠正",
    r"纠正一下",
    r"请纠正",
    r"以后",
    r"禁止",
    r"严禁",
    r"务必",
    r"只能",
    r"不许",
    r"别",
]

_CONSTRAINT_PATTERNS = [
    # 以后默认... / 以后都...
    r"^以后(?:默认|都|请|要|应该)?[\s,，]*",
    # 不要... / 别...
    r"^(?:不要|别|禁止|严禁|不许)[\s,，]*",
    # 必须... / 务必... / 只能...
    r"^(?:必须|务必|只能)[\s,，]*",
    # 记住... / 记住了...
    r"^(?:记住|记住了|记一下|记下来)[\s,，]*",
    # 纠正... / 纠正一下...
    r"^(?:纠正|纠正一下|请纠正|你错了|不对)[\s,，]*",
    # 不要改...
    r"^(?:不要改|别改|不许改|禁止改)[\s,，]*",
]


def should_build_runtime_query_index(user_text: str) -> bool:
    """Check if user_text is a strong-constraint instruction.

    Matches patterns like:
        - 以后默认...
        - 不要...
        - 必须...
        - 记住...
        - 纠正系统行为的话术
        - 不要改现有结构

    Args:
        user_text: Raw user input text.

    Returns:
        True if the text should be indexed as a runtime query.
    """
    if not user_text or not isinstance(user_text, str):
        return False

    text = user_text.strip()
    if len(text) < 3:
        return False

    for pattern in _CONSTRAINT_PATTERNS:
        if re.search(pattern, text, re.IGNORECASE):
            return True

    return False


def _normalize_for_dedup(text: str) -> str:
    """Normalize text for deduplication comparison."""
    text = text.strip().lower()
    # Remove punctuation and extra spaces
    text = re.sub(r"[\s,，.。!！?？、；：\"\"''()（）【】\[\]]+", "", text)
    return text


def _is_similar(a: str, b: str, threshold: float = 0.75) -> bool:
    """Check if two texts are similar enough to be considered duplicates."""
    na = _normalize_for_dedup(a)
    nb = _normalize_for_dedup(b)

    if not na or not nb:
        return False

    # Exact match after normalization
    if na == nb:
        return True

    # Substring containment (one contains the other)
    if na in nb or nb in na:
        return True

    # Jaccard similarity on character sets
    set_a = set(na)
    set_b = set(nb)
    intersection = len(set_a & set_b)
    union = len(set_a | set_b)
    if union == 0:
        return False

    return (intersection / union) >= threshold


def _get_runtime_index_path(memory_root: str | Path, chat_id: str) -> Path:
    """Get the runtime index file path for a chat session."""
    root = Path(memory_root)
    runtime_dir = root / ".runtime" / "session_queries"
    return runtime_dir / f"{chat_id}.json"


def append_runtime_query_index(
    memory_root: str | Path,
    chat_id: str,
    user_text: str,
    metadata: dict[str, Any] | None = None,
) -> RuntimeQueryIndex:
    """Append a user instruction to the runtime query index.

    - Skips if user_text is not a strong-constraint instruction
    - Removes similar existing entries (deduplication)
    - Keeps at most _MAX_ENTRIES recent entries
    - Does NOT write to long-term .memory/*.json

    Args:
        memory_root: Root directory of the memory store (e.g., ".memory")
        chat_id: Unique chat session identifier
        user_text: Raw user input text
        metadata: Optional metadata dict (e.g., timestamp, source)

    Returns:
        Updated RuntimeQueryIndex
    """
    if not should_build_runtime_query_index(user_text):
        # Load and return existing index without modification
        return load_runtime_query_index(memory_root, chat_id)

    index = load_runtime_query_index(memory_root, chat_id)

    # Remove similar existing entries (new instruction overrides old similar ones)
    index.entries = [
        e for e in index.entries
        if not _is_similar(e.text, user_text)
    ]

    # Append new entry
    entry = RuntimeQueryEntry(
        text=user_text.strip(),
        created_at=datetime.now(timezone.utc).isoformat(),
        metadata=metadata or {},
    )
    index.entries.append(entry)

    # Trim to max capacity (keep most recent)
    if len(index.entries) > _MAX_ENTRIES:
        index.entries = index.entries[-_MAX_ENTRIES:]

    # Persist
    index_path = _get_runtime_index_path(memory_root, chat_id)
    index_path.parent.mkdir(parents=True, exist_ok=True)
    index_path.write_text(
        index.model_dump_json(indent=2, ensure_ascii=False),
        encoding="utf-8",
    )

    return index


def load_runtime_query_index(
    memory_root: str | Path,
    chat_id: str,
) -> RuntimeQueryIndex:
    """Load the runtime query index for a chat session.

    Args:
        memory_root: Root directory of the memory store
        chat_id: Unique chat session identifier

    Returns:
        RuntimeQueryIndex (empty if file doesn't exist)
    """
    index_path = _get_runtime_index_path(memory_root, chat_id)

    if not index_path.exists():
        return RuntimeQueryIndex(chat_id=chat_id)

    try:
        content = index_path.read_text(encoding="utf-8")
        data = json.loads(content)
        return RuntimeQueryIndex.model_validate(data)
    except Exception:
        return RuntimeQueryIndex(chat_id=chat_id)


_RUNTIME_SOURCE_WEIGHT = 12.0


def build_runtime_sections(
    memory_root: str,
    chat_id: str | None,
) -> list[MemoryItem]:
    """Load runtime query index and convert entries to high-weight MemoryItems.

    Returns empty list if:
    - chat_id is missing
    - runtime index file does not exist
    """
    if not chat_id:
        return []

    try:
        runtime_index = load_runtime_query_index(memory_root, chat_id)
    except Exception:
        return []

    if not runtime_index.entries:
        return []

    items: list[MemoryItem] = []
    for entry in runtime_index.entries:
        items.append(MemoryItem(
            content=entry.text,
            content_type="rule",
            speed_lookup=entry.text[:60],
            source="explicit",
            source_id=f"runtime:{chat_id}",
            priority=_RUNTIME_SOURCE_WEIGHT,
            retrieval=RetrievalHints(),
        ))

    return items
