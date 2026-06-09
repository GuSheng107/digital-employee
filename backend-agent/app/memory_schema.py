"""记忆数据模式定义模块——记忆文件格式的唯一事实来源。

所有记忆文件以 JSON 格式存储（非 Markdown），每个文件包含一组 MemoryItem 对象，
具有内容、检索提示和元数据等结构化字段。

本模块提供：
- 记忆条目和文件的 Pydantic 模型定义
- 内容类型枚举
- 文件类型枚举
- JSON 文件的读写工具（支持原子写入和目录锁）
"""
from __future__ import annotations

import json
import logging
import os
import tempfile
import uuid
from datetime import datetime
from pathlib import Path
from typing import Literal

from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)


ContentType = Literal[
    "problem_solution",
    "qa",
    "term_definition",
    "operation_guide",
    "configuration",
    "process",
    "rule",
    "fact",
    "preference",
    "comparison",
]

MemoryFileKey = Literal[
    "explicit",
    "profile",
    "work",
    "inbox",
    "rules",
    "changelog",
]

MEMORY_FILE_PRIORITIES: dict[str, float] = {
    "explicit": 10.0,
    "work": 8.0,
    "profile": 6.0,
    "document": 5.0,
    "timeline": 4.0,
    "rules": 3.0,
    "inbox": 2.0,
    "changelog": 1.0,
}

MEMORY_FILE_LABELS: dict[str, str] = {
    "explicit": "显式记忆",
    "profile": "用户画像",
    "work": "工作笔记",
    "inbox": "收件箱",
    "rules": "记忆规则",
    "changelog": "变更日志",
    "document": "文档记忆",
    "timeline": "时间线",
}


class RetrievalHints(BaseModel):
    keywords: list[str] = Field(default_factory=list)
    boost: float = 1.0
    tags: list[str] = Field(default_factory=list)
    terms: list[str] = Field(default_factory=list)
    aliases: list[str] = Field(default_factory=list)
    entities: list[str] = Field(default_factory=list)


class MemoryItem(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    content: str = ""
    content_type: ContentType = "fact"
    speed_lookup: str = ""
    retrieval: RetrievalHints = Field(default_factory=RetrievalHints)
    source: Literal["chat", "document", "explicit", "manual"] = "chat"
    source_id: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    priority: float = 1.0


class MemoryFile(BaseModel):
    version: int = 1
    file_key: str = ""
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    items: list[MemoryItem] = Field(default_factory=list)


class ChangelogEntry(BaseModel):
    id: str = Field(default_factory=lambda: str(uuid.uuid4()))
    action: Literal["add", "update", "delete", "compress", "promote", "merge", "archive", "patch"] = "add"
    target_file: str = ""
    item_id: str = ""
    item_content_preview: str = ""
    reason: str = ""
    created_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))


class ChangelogFile(BaseModel):
    version: int = 1
    entries: list[ChangelogEntry] = Field(default_factory=list)


class TimelineFile(BaseModel):
    version: int = 1
    month: str = ""
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    items: list[MemoryItem] = Field(default_factory=list)


class DocumentMemoryFile(BaseModel):
    version: int = 1
    source_id: str = ""
    source_filename: str = ""
    updated_at: str = Field(default_factory=lambda: datetime.now().isoformat(timespec="seconds"))
    items: list[MemoryItem] = Field(default_factory=list)


MEMORY_JSON_FILES: dict[str, str] = {
    "explicit": "explicit.json",
    "profile": "profile.json",
    "work": "work.json",
    "inbox": "inbox.json",
    "rules": "rules.json",
}


def _acquire_dir_lock(dir_path: Path, timeout: float = 5.0) -> Path:
    lock_path = dir_path / ".lock"
    dir_path.mkdir(parents=True, exist_ok=True)
    import time
    deadline = time.monotonic() + timeout
    while True:
        try:
            fd = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_WRONLY)
            os.write(fd, str(os.getpid()).encode())
            os.close(fd)
            return lock_path
        except FileExistsError:
            if time.monotonic() > deadline:
                raise RuntimeError(f"Could not acquire directory lock: {lock_path}")
            time.sleep(0.05)


def _release_dir_lock(lock_path: Path) -> None:
    try:
        lock_path.unlink()
    except FileNotFoundError:
        pass


def _write_text_atomic(target: Path, text: str) -> None:
    target.parent.mkdir(parents=True, exist_ok=True)
    fd, tmp_path = tempfile.mkstemp(
        dir=str(target.parent),
        prefix=".tmp_",
        suffix=".json",
    )
    try:
        with os.fdopen(fd, "w", encoding="utf-8") as f:
            f.write(text)
        os.replace(tmp_path, str(target))
    except BaseException:
        try:
            os.unlink(tmp_path)
        except OSError:
            pass
        raise


def load_memory_file(memory_root: str | Path, file_key: str) -> MemoryFile:
    root = Path(memory_root)
    filename = MEMORY_JSON_FILES.get(file_key, f"{file_key}.json")
    path = root / filename
    if not path.exists():
        return MemoryFile(file_key=file_key)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        data.setdefault("file_key", file_key)
        return MemoryFile.model_validate(data)
    except Exception as exc:
        logger.error("Failed to load memory file %s: %s", path, exc)
        return MemoryFile(file_key=file_key)


def save_memory_file(memory_root: str | Path, mf: MemoryFile) -> None:
    root = Path(memory_root)
    filename = MEMORY_JSON_FILES.get(mf.file_key, f"{mf.file_key}.json")
    path = root / filename
    mf.updated_at = datetime.now().isoformat(timespec="seconds")
    lock_path = _acquire_dir_lock(root)
    try:
        text = mf.model_dump_json(indent=2, ensure_ascii=False)
        _write_text_atomic(path, text)
    finally:
        _release_dir_lock(lock_path)


def load_changelog(memory_root: str | Path) -> ChangelogFile:
    root = Path(memory_root)
    path = root / "changelog.json"
    if not path.exists():
        return ChangelogFile()
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return ChangelogFile.model_validate(data)
    except Exception as exc:
        logger.error("Failed to load changelog: %s", exc)
        return ChangelogFile()


def save_changelog(memory_root: str | Path, cf: ChangelogFile) -> None:
    root = Path(memory_root)
    path = root / "changelog.json"
    lock_path = _acquire_dir_lock(root)
    try:
        text = cf.model_dump_json(indent=2, ensure_ascii=False)
        _write_text_atomic(path, text)
    finally:
        _release_dir_lock(lock_path)


def load_timeline_file(memory_root: str | Path, month: str) -> TimelineFile:
    root = Path(memory_root)
    path = root / "timeline" / f"{month}.json"
    if not path.exists():
        return TimelineFile(month=month)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return TimelineFile.model_validate(data)
    except Exception as exc:
        logger.error("Failed to load timeline %s: %s", month, exc)
        return TimelineFile(month=month)


def save_timeline_file(memory_root: str | Path, tf: TimelineFile) -> None:
    root = Path(memory_root)
    path = root / "timeline" / f"{tf.month}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    tf.updated_at = datetime.now().isoformat(timespec="seconds")
    lock_path = _acquire_dir_lock(root)
    try:
        text = tf.model_dump_json(indent=2, ensure_ascii=False)
        _write_text_atomic(path, text)
    finally:
        _release_dir_lock(lock_path)


def load_document_memory(memory_root: str | Path, source_id: str) -> DocumentMemoryFile:
    root = Path(memory_root)
    path = root / "documents" / f"{source_id}.json"
    if not path.exists():
        return DocumentMemoryFile(source_id=source_id)
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
        return DocumentMemoryFile.model_validate(data)
    except Exception as exc:
        logger.error("Failed to load document memory %s: %s", source_id, exc)
        return DocumentMemoryFile(source_id=source_id)


def save_document_memory(memory_root: str | Path, dm: DocumentMemoryFile) -> None:
    root = Path(memory_root)
    path = root / "documents" / f"{dm.source_id}.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    dm.updated_at = datetime.now().isoformat(timespec="seconds")
    lock_path = _acquire_dir_lock(root)
    try:
        text = dm.model_dump_json(indent=2, ensure_ascii=False)
        _write_text_atomic(path, text)
    finally:
        _release_dir_lock(lock_path)


def add_changelog_entry(
    memory_root: str | Path,
    *,
    action: str,
    target_file: str,
    item_id: str = "",
    item_content_preview: str = "",
    reason: str = "",
) -> None:
    cf = load_changelog(memory_root)
    cf.entries.append(ChangelogEntry(
        action=action,
        target_file=target_file,
        item_id=item_id,
        item_content_preview=item_content_preview[:100],
        reason=reason,
    ))
    if len(cf.entries) > 500:
        cf.entries = cf.entries[-500:]
    save_changelog(memory_root, cf)


def list_timeline_months(memory_root: str | Path, limit: int | None = 0) -> list[str]:
    root = Path(memory_root) / "timeline"
    if not root.exists():
        return []
    months: list[str] = []
    for p in sorted(root.glob("*.json"), reverse=True):
        months.append(p.stem)
    if limit is None or int(limit) <= 0:
        return months
    return months[:int(limit)]


def list_document_source_ids(memory_root: str | Path) -> list[str]:
    root = Path(memory_root) / "documents"
    if not root.exists():
        return []
    return [p.stem for p in sorted(root.glob("*.json"))]
