from __future__ import annotations

import logging
from pathlib import Path
from typing import Any

from app.memory_schema import (
    load_memory_file,
    load_timeline_file,
    load_document_memory,
    list_timeline_months,
    list_document_source_ids,
    MemoryFile,
    MemoryItem,
    MEMORY_JSON_FILES,
)

logger = logging.getLogger(__name__)


class JsonLoader:
    def __init__(self, memory_root: str | Path = ".memory") -> None:
        self.memory_root = Path(memory_root)

    def load_all_files(self) -> dict[str, MemoryFile]:
        files: dict[str, MemoryFile] = {}
        for file_key in MEMORY_JSON_FILES:
            mf = load_memory_file(self.memory_root, file_key)
            if mf.items:
                files[file_key] = mf
        for month in list_timeline_months(self.memory_root):
            tf = load_timeline_file(self.memory_root, month)
            if tf.items:
                files[f"timeline/{month}"] = MemoryFile(
                    file_key=f"timeline/{month}",
                    items=tf.items,
                    updated_at=tf.updated_at,
                )
        for source_id in list_document_source_ids(self.memory_root):
            dm = load_document_memory(self.memory_root, source_id)
            if dm.items:
                files[f"documents/{source_id}"] = MemoryFile(
                    file_key=f"documents/{source_id}",
                    items=dm.items,
                    updated_at=dm.updated_at,
                )
        return files

    def load_file(self, file_key: str) -> MemoryFile:
        if file_key.startswith("timeline/"):
            month = file_key.split("/", 1)[1]
            tf = load_timeline_file(self.memory_root, month)
            return MemoryFile(file_key=file_key, items=tf.items, updated_at=tf.updated_at)
        if file_key.startswith("documents/"):
            source_id = file_key.split("/", 1)[1]
            dm = load_document_memory(self.memory_root, source_id)
            return MemoryFile(file_key=file_key, items=dm.items, updated_at=dm.updated_at)
        return load_memory_file(self.memory_root, file_key)
