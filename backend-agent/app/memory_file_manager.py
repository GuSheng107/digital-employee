from __future__ import annotations

"""记忆文件存储与检索管理模块。

管理记忆文件的目录初始化、文件列表查询、条目的增删改查、
关键词搜索、文档记忆源的预览与删除等操作，支持核心记忆、
时间线和文档记忆三种文件类型。
"""

import logging
import sys
from pathlib import Path
from typing import Any

import re

from app.memory_schema import (
    MemoryItem, MemoryFile, RetrievalHints,
    load_memory_file, save_memory_file,
    load_changelog, save_changelog, add_changelog_entry,
    load_timeline_file, save_timeline_file,
    load_document_memory, save_document_memory,
    list_timeline_months, list_document_source_ids,
    MEMORY_JSON_FILES, MEMORY_FILE_LABELS, MEMORY_FILE_PRIORITIES,
)

logger = logging.getLogger(__name__)

_UUID_RE = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$", re.IGNORECASE)


def _fallback_label(source_id: str) -> str:
    if _UUID_RE.match(source_id):
        return f"文档 {source_id[:8]}…"
    return f"文档 {source_id}"


def _load_reader_scorer():
    project_root = Path(__file__).resolve().parent.parent
    reader_script = project_root / ".skills" / "system" / "memory-reader" / "script"
    if reader_script.exists() and str(reader_script) not in sys.path:
        sys.path.insert(0, str(reader_script))
    from memory_reader.orchestrator import _file_weight_for_key
    from memory_reader.selection.json_scorer import score_memory_items

    return score_memory_items, _file_weight_for_key


class MemoryFileManager:
    def __init__(self, memory_root: str | Path = ".memory") -> None:
        self.memory_root = Path(memory_root)

    def init_memory_dir(self) -> None:
        self.memory_root.mkdir(parents=True, exist_ok=True)
        (self.memory_root / "documents").mkdir(parents=True, exist_ok=True)
        (self.memory_root / "timeline").mkdir(parents=True, exist_ok=True)
        for file_key in MEMORY_JSON_FILES:
            mf = load_memory_file(self.memory_root, file_key)
            save_memory_file(self.memory_root, mf)

    def list_files(self, document_labels: dict[str, str] | None = None) -> list[dict[str, Any]]:
        document_labels = document_labels or {}
        result = []
        for file_key, filename in MEMORY_JSON_FILES.items():
            mf = load_memory_file(self.memory_root, file_key)
            result.append({
                "file_key": file_key,
                "filename": filename,
                "label": MEMORY_FILE_LABELS.get(file_key, file_key),
                "item_count": len(mf.items),
                "updated_at": mf.updated_at,
            })
        for month in list_timeline_months(self.memory_root):
            tf = load_timeline_file(self.memory_root, month)
            result.append({
                "file_key": f"timeline/{month}",
                "filename": f"timeline/{month}.json",
                "label": f"时间线 {month}",
                "item_count": len(tf.items),
                "updated_at": tf.updated_at,
            })
        for source_id in list_document_source_ids(self.memory_root):
            dm = load_document_memory(self.memory_root, source_id)
            label = (
                str(document_labels.get(source_id) or "").strip()
                or str(dm.source_filename or "").strip()
                or _fallback_label(source_id)
            )
            result.append({
                "file_key": f"documents/{source_id}",
                "filename": f"documents/{source_id}.json",
                "label": label,
                "source_id": source_id,
                "item_count": len(dm.items),
                "updated_at": dm.updated_at,
            })
        return result

    def get_items(self, file_key: str) -> list[MemoryItem]:
        if file_key.startswith("timeline/"):
            month = file_key.split("/", 1)[1]
            tf = load_timeline_file(self.memory_root, month)
            return tf.items
        if file_key.startswith("documents/"):
            source_id = file_key.split("/", 1)[1]
            dm = load_document_memory(self.memory_root, source_id)
            return dm.items
        mf = load_memory_file(self.memory_root, file_key)
        return mf.items

    def get_item(self, file_key: str, item_id: str) -> MemoryItem | None:
        items = self.get_items(file_key)
        for item in items:
            if item.id == item_id:
                return item
        return None

    def add_item(self, file_key: str, item: MemoryItem) -> MemoryItem:
        if file_key.startswith("timeline/"):
            month = file_key.split("/", 1)[1]
            tf = load_timeline_file(self.memory_root, month)
            tf.items.append(item)
            save_timeline_file(self.memory_root, tf)
        elif file_key.startswith("documents/"):
            source_id = file_key.split("/", 1)[1]
            dm = load_document_memory(self.memory_root, source_id)
            dm.items.append(item)
            save_document_memory(self.memory_root, dm)
        else:
            mf = load_memory_file(self.memory_root, file_key)
            mf.items.append(item)
            save_memory_file(self.memory_root, mf)
        add_changelog_entry(self.memory_root, action="add", target_file=file_key, item_id=item.id, item_content_preview=item.content)
        return item

    def update_item(self, file_key: str, item_id: str, updates: dict[str, Any]) -> MemoryItem | None:
        from datetime import datetime
        items = self.get_items(file_key)
        for i, item in enumerate(items):
            if item.id == item_id:
                for key, value in updates.items():
                    if hasattr(item, key):
                        setattr(item, key, value)
                item.updated_at = datetime.now().isoformat(timespec="seconds")
                self._save_items(file_key, items)
                add_changelog_entry(self.memory_root, action="update", target_file=file_key, item_id=item_id, item_content_preview=item.content[:100])
                return item
        return None

    def delete_item(self, file_key: str, item_id: str) -> bool:
        items = self.get_items(file_key)
        original_len = len(items)
        items = [item for item in items if item.id != item_id]
        if len(items) == original_len:
            return False
        self._save_items(file_key, items)
        add_changelog_entry(self.memory_root, action="delete", target_file=file_key, item_id=item_id)
        return True

    def search_items(self, query: str, file_key: str | None = None) -> list[dict[str, Any]]:
        results = []
        if file_key:
            file_keys = [file_key]
        else:
            file_keys = list(MEMORY_JSON_FILES.keys())
            file_keys.extend(f"timeline/{month}" for month in list_timeline_months(self.memory_root))
            file_keys.extend(f"documents/{source_id}" for source_id in list_document_source_ids(self.memory_root))

        try:
            score_memory_items, file_weight_for_key = _load_reader_scorer()
        except Exception as exc:
            logger.warning("Failed to load memory reader scorer, falling back to simple search: %s", exc)
            score_memory_items = None
            file_weight_for_key = None

        for fk in file_keys:
            items = self.get_items(fk)
            if score_memory_items is not None and file_weight_for_key is not None:
                scored = score_memory_items(
                    items,
                    query,
                    file_weight=file_weight_for_key(fk),
                )
                for item, score in scored:
                    if score > 0:
                        results.append({
                            "file_key": fk,
                            "item": item,
                            "score": score,
                        })
                continue

            query_lower = query.lower()
            query_terms = set(re.split(r'[\s,，|｜、]+', query_lower)) - {''}
            for item in items:
                score = 0.0
                if item.speed_lookup:
                    lookup_terms = set(re.split(r'[|｜,，\s]+', item.speed_lookup.lower())) - {''}
                    for qt in query_terms:
                        for lt in lookup_terms:
                            if qt == lt:
                                score += 10.0
                            elif qt in lt or lt in qt:
                                score += 5.0
                content_lower = item.content.lower()
                for qt in query_terms:
                    if qt in content_lower:
                        score += 3.0
                if score > 0:
                    results.append({
                        "file_key": fk,
                        "item": item,
                        "score": score,
                    })

        results.sort(key=lambda x: x["score"], reverse=True)
        return results

    def _save_items(self, file_key: str, items: list[MemoryItem]) -> None:
        from datetime import datetime
        if file_key.startswith("timeline/"):
            month = file_key.split("/", 1)[1]
            tf = load_timeline_file(self.memory_root, month)
            tf.items = items
            save_timeline_file(self.memory_root, tf)
        elif file_key.startswith("documents/"):
            source_id = file_key.split("/", 1)[1]
            dm = load_document_memory(self.memory_root, source_id)
            dm.items = items
            save_document_memory(self.memory_root, dm)
        else:
            mf = load_memory_file(self.memory_root, file_key)
            mf.items = items
            save_memory_file(self.memory_root, mf)

    def preview_remove_document_source(self, source_id: str) -> dict[str, Any]:
        if not source_id.strip():
            return {"affected_files": [], "memory_items_count": 0, "document_exists": False}
        affected_files: list[str] = []
        memory_items_count = 0
        document_exists = False
        doc_path = self.memory_root / "documents" / f"{source_id}.json"
        if doc_path.exists():
            document_exists = True
            dm = load_document_memory(self.memory_root, source_id)
            memory_items_count = len(dm.items)
            affected_files.append(f"documents/{source_id}.json")
        for file_key in MEMORY_JSON_FILES:
            mf = load_memory_file(self.memory_root, file_key)
            matching = [it for it in mf.items if it.source_id == source_id]
            if matching:
                affected_files.append(f"{file_key}.json")
        return {
            "affected_files": affected_files,
            "memory_items_count": memory_items_count,
            "document_exists": document_exists,
        }

    def remove_document_source(self, source_id: str) -> list[str]:
        if not source_id.strip():
            return []
        updated_files: list[str] = []
        doc_path = self.memory_root / "documents" / f"{source_id}.json"
        if doc_path.exists():
            try:
                doc_path.unlink(missing_ok=True)
            except PermissionError:
                doc_path.write_text("{}", encoding="utf-8")
            updated_files.append(str(doc_path))
        for file_key in MEMORY_JSON_FILES:
            mf = load_memory_file(self.memory_root, file_key)
            original_len = len(mf.items)
            mf.items = [it for it in mf.items if it.source_id != source_id]
            if len(mf.items) < original_len:
                save_memory_file(self.memory_root, mf)
                updated_files.append(str(self.memory_root / MEMORY_JSON_FILES[file_key]))
        if updated_files:
            add_changelog_entry(
                self.memory_root,
                action="delete",
                target_file=f"documents/{source_id}",
                item_id="",
                item_content_preview=f"已删除文档 {source_id} 及其关联记忆",
            )
        return updated_files
