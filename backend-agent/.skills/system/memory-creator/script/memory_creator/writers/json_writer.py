from __future__ import annotations

import logging
import re
from pathlib import Path
from typing import Any

from app.memory_schema import (
    MemoryItem,
    MemoryFile,
    DocumentMemoryFile,
    TimelineFile,
    load_memory_file,
    save_memory_file,
    load_document_memory,
    save_document_memory,
    load_timeline_file,
    save_timeline_file,
    list_document_source_ids,
    list_timeline_months,
    add_changelog_entry,
    MEMORY_JSON_FILES,
)

CONFIDENCE_THRESHOLD = 0.7
SIMILARITY_THRESHOLD = 0.7

logger = logging.getLogger(__name__)


class JsonWriter:
    def __init__(self, memory_dir: str | Path = ".memory") -> None:
        self.memory_dir = Path(memory_dir)

    def init_memory_dir(self) -> list[str]:
        self.memory_dir.mkdir(parents=True, exist_ok=True)
        (self.memory_dir / "documents").mkdir(parents=True, exist_ok=True)
        (self.memory_dir / "timeline").mkdir(parents=True, exist_ok=True)

        created: list[str] = []
        for file_key, filename in MEMORY_JSON_FILES.items():
            path = self.memory_dir / filename
            if not path.exists():
                mf = MemoryFile(file_key=file_key)
                save_memory_file(str(self.memory_dir), mf)
                created.append(str(path))
        return created

    def _jaccard_similarity(self, a: str, b: str) -> float:
        a_set = set(a[i:i+2] for i in range(len(a) - 1))
        b_set = set(b[i:i+2] for i in range(len(b) - 1))
        if not a_set and not b_set:
            return 1.0
        if not a_set or not b_set:
            return 0.0
        return len(a_set & b_set) / len(a_set | b_set)

    def _is_duplicate(self, new_item: MemoryItem, existing_items: list[MemoryItem]) -> bool:
        new_content = new_item.content.strip().lower()
        if not new_content:
            return True
        for existing in existing_items:
            if existing.content.strip().lower() == new_content:
                return True
            if self._jaccard_similarity(new_content, existing.content.strip().lower()) >= SIMILARITY_THRESHOLD:
                return True
        return False

    def _normalize_duplicate_text(self, text: str) -> str:
        value = str(text or "").lower()
        value = re.sub(r"(问题|答案|原因|解决|事实|术语|查询词|来源|记忆|内容)[:：]", "", value)
        return re.sub(r"[\s,，。.!！?？:：;；|｜/\\()\[\]{}<>《》\"'`_-]+", "", value)

    def _is_priority_duplicate(self, new_item: MemoryItem, existing_item: MemoryItem) -> bool:
        new_content = self._normalize_duplicate_text(new_item.content)
        existing_content = self._normalize_duplicate_text(existing_item.content)
        if not new_content or not existing_content:
            return False
        if new_content == existing_content:
            return True
        shorter = min(len(new_content), len(existing_content))
        if shorter >= 18 and (new_content in existing_content or existing_content in new_content):
            return True
        return self._jaccard_similarity(new_content, existing_content) >= 0.86

    def _iter_document_items(self) -> list[MemoryItem]:
        items: list[MemoryItem] = []
        for source_id in list_document_source_ids(str(self.memory_dir)):
            items.extend(load_document_memory(str(self.memory_dir), source_id).items)
        return items

    def _iter_source_items(self, source: str) -> list[MemoryItem]:
        items: list[MemoryItem] = []
        for file_key in MEMORY_JSON_FILES:
            mf = load_memory_file(str(self.memory_dir), file_key)
            items.extend([item for item in mf.items if str(item.source or "") == source])
        for month in list_timeline_months(str(self.memory_dir), limit=1000):
            tf = load_timeline_file(str(self.memory_dir), month)
            items.extend([item for item in tf.items if str(item.source or "") == source])
        for source_id in list_document_source_ids(str(self.memory_dir)):
            dm = load_document_memory(str(self.memory_dir), source_id)
            items.extend([item for item in dm.items if str(item.source or "") == source])
        return items

    def _is_duplicate_across_files(self, new_item: MemoryItem, exclude_file: str) -> bool:
        new_content = new_item.content.strip().lower()
        if not new_content:
            return True
        for file_key in MEMORY_JSON_FILES:
            filename = MEMORY_JSON_FILES[file_key]
            if filename == exclude_file:
                continue
            mf = load_memory_file(str(self.memory_dir), file_key)
            for existing in mf.items:
                if existing.content.strip().lower() == new_content:
                    return True
        return False

    def _is_duplicate_against_higher_priority(
        self,
        new_item: MemoryItem,
        *,
        target_file: str,
        source_type: str,
    ) -> bool:
        target_key = self._target_file_to_key(target_file)
        if target_key == "explicit":
            return False

        higher_items: list[MemoryItem] = []
        higher_items.extend(load_memory_file(str(self.memory_dir), "explicit").items)
        higher_items.extend(self._iter_source_items("explicit"))

        if source_type == "chat":
            higher_items.extend(self._iter_document_items())
            higher_items.extend(self._iter_source_items("document"))

        return any(self._is_priority_duplicate(new_item, existing) for existing in higher_items)

    def _add_items_to_file(self, file_key: str, items: list[MemoryItem]) -> None:
        mf = load_memory_file(str(self.memory_dir), file_key)
        for item in items:
            if not self._is_duplicate(item, mf.items):
                mf.items.append(item)
        save_memory_file(str(self.memory_dir), mf)

    def _add_items_to_timeline(self, month: str, items: list[MemoryItem]) -> None:
        tf = load_timeline_file(str(self.memory_dir), month)
        for item in items:
            if not self._is_duplicate(item, tf.items):
                tf.items.append(item)
        save_timeline_file(str(self.memory_dir), tf)

    def _add_items_to_document(self, source_id: str, items: list[MemoryItem], source_filename: str = "") -> None:
        dm = load_document_memory(str(self.memory_dir), source_id)
        for item in items:
            if not self._is_duplicate(item, dm.items):
                dm.items.append(item)
        if source_filename and not dm.source_filename:
            dm.source_filename = source_filename
        save_document_memory(str(self.memory_dir), dm)

    def _remove_source_items(self, source_id: str, source_filename: str = "") -> list[str]:
        if not source_id:
            return []

        updated_files: list[str] = []
        for file_key, filename in MEMORY_JSON_FILES.items():
            mf = load_memory_file(str(self.memory_dir), file_key)
            before = len(mf.items)
            mf.items = [item for item in mf.items if str(item.source_id or "") != source_id]
            if len(mf.items) != before:
                save_memory_file(str(self.memory_dir), mf)
                updated_files.append(str(self.memory_dir / filename))

        for month in list_timeline_months(str(self.memory_dir), limit=1000):
            tf = load_timeline_file(str(self.memory_dir), month)
            before = len(tf.items)
            tf.items = [item for item in tf.items if str(item.source_id or "") != source_id]
            if len(tf.items) != before:
                save_timeline_file(str(self.memory_dir), tf)
                updated_files.append(str(self.memory_dir / "timeline" / f"{month}.json"))

        dm = load_document_memory(str(self.memory_dir), source_id)
        if dm.items or (source_filename and dm.source_filename != source_filename):
            dm.items = []
            if source_filename:
                dm.source_filename = source_filename
            save_document_memory(str(self.memory_dir), dm)
            updated_files.append(str(self.memory_dir / "documents" / f"{source_id}.json"))

        return updated_files

    def write_candidates(
        self,
        candidates: list[Any],
        *,
        source_type: str = "",
        source_id: str = "",
        source_filename: str = "",
        mode: str = "append",
        split_index: int = 0,
        split_total: int = 0,
    ) -> list[str]:
        grouped: dict[str, list[Any]] = {}
        for c in candidates:
            target = c.target_file
            grouped.setdefault(target, []).append(c)

        updated_files: list[str] = []
        if mode == "update":
            updated_files.extend(self._remove_source_items(source_id, source_filename=source_filename))

        for target_file, file_candidates in grouped.items():
            high_confidence: list[MemoryItem] = []
            low_confidence: list[MemoryItem] = []

            for c in file_candidates:
                item = c.item
                if getattr(c, "confidence", 1.0) < CONFIDENCE_THRESHOLD:
                    low_confidence.append(item)
                else:
                    high_confidence.append(item)

            if target_file.startswith("documents/"):
                doc_id = target_file.replace("documents/", "").replace(".json", "")
                if high_confidence:
                    self._add_items_to_document(doc_id, high_confidence, source_filename=source_filename)
                    updated_files.append(str(self.memory_dir / "documents" / f"{doc_id}.json"))
                if low_confidence:
                    self._add_items_to_file("inbox", low_confidence)
                    updated_files.append(str(self.memory_dir / "inbox.json"))
            elif target_file.startswith("timeline/"):
                month = target_file.replace("timeline/", "").replace(".json", "")
                all_items = high_confidence + low_confidence
                if all_items:
                    self._add_items_to_timeline(month, all_items)
                    updated_files.append(str(self.memory_dir / "timeline" / f"{month}.json"))
            else:
                file_key = self._target_file_to_key(target_file)
                if not high_confidence:
                    if low_confidence:
                        self._add_items_to_file("inbox", low_confidence)
                        updated_files.append(str(self.memory_dir / "inbox.json"))
                    continue

                filtered: list[MemoryItem] = []
                for item in high_confidence:
                    if self._is_duplicate_against_higher_priority(
                        item,
                        target_file=target_file,
                        source_type=source_type,
                    ):
                        continue
                    if source_type != "document" and self._is_duplicate_across_files(item, target_file):
                        continue
                    filtered.append(item)
                high_confidence = filtered

                if high_confidence:
                    self._add_items_to_file(file_key, high_confidence)
                    updated_files.append(str(self.memory_dir / MEMORY_JSON_FILES.get(file_key, f"{file_key}.json")))

                if low_confidence:
                    self._add_items_to_file("inbox", low_confidence)
                    updated_files.append(str(self.memory_dir / "inbox.json"))

        return list(dict.fromkeys(updated_files))

    def _target_file_to_key(self, target_file: str) -> str:
        base = target_file.replace(".json", "").replace(".md", "")
        mapping = {
            "explicit": "explicit",
            "profile": "profile",
            "work": "work",
            "inbox": "inbox",
            "rules": "rules",
        }
        return mapping.get(base, base)
