from __future__ import annotations

import hashlib
import re
from pathlib import Path
from typing import Any
from urllib.parse import quote

ATTACHMENTS_DIR_NAME = ".attachments"
_INVALID_FILENAME_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
_MAX_STORAGE_NAME_LENGTH = 180


def get_attachments_dir(project_root: Path) -> Path:
    """获取附件存储目录"""
    attachments_dir = project_root / ATTACHMENTS_DIR_NAME
    attachments_dir.mkdir(exist_ok=True)
    return attachments_dir


def compute_file_hash(content: bytes) -> str:
    """计算文件内容的哈希值"""
    return hashlib.sha256(content).hexdigest()


def _infer_kind_from_mime(mime_type: str) -> str:
    if not mime_type:
        return "file"
    normalized = mime_type.strip().lower().split(";")[0].strip()
    if normalized.startswith("image/"):
        return "image"
    if normalized.startswith("video/"):
        return "video"
    if normalized.startswith("audio/"):
        return "audio"
    return "file"


def build_attachment_url(storage_name: str) -> str:
    return f"/api/manual-reply-attachments/{quote(storage_name)}"


def _sanitize_storage_filename(filename: str) -> str:
    raw_name = Path(str(filename or "").strip()).name
    if not raw_name:
        raw_name = "attachment"

    stem = Path(raw_name).stem or "attachment"
    suffix = Path(raw_name).suffix
    stem = _INVALID_FILENAME_CHARS.sub("_", stem).strip(" .")
    suffix = _INVALID_FILENAME_CHARS.sub("_", suffix).strip(" .")

    if not stem:
        stem = "attachment"
    if suffix and not suffix.startswith("."):
        suffix = f".{suffix}"

    max_stem_length = max(1, _MAX_STORAGE_NAME_LENGTH - len(suffix))
    stem = stem[:max_stem_length].rstrip(" .") or "attachment"
    return f"{stem}{suffix}"


def _dedupe_storage_filename(attachments_dir: Path, storage_name: str) -> str:
    candidate = storage_name
    stem = Path(storage_name).stem or "attachment"
    suffix = Path(storage_name).suffix
    counter = 2
    while (attachments_dir / candidate).exists():
        duplicate_suffix = f" ({counter})"
        max_stem_length = max(1, _MAX_STORAGE_NAME_LENGTH - len(suffix) - len(duplicate_suffix))
        trimmed_stem = stem[:max_stem_length].rstrip(" .") or "attachment"
        candidate = f"{trimmed_stem}{duplicate_suffix}{suffix}"
        counter += 1
    return candidate


def persist_attachment(
    project_root: Path,
    filename: str,
    content: bytes,
    mime_type: str = "",
) -> dict[str, Any]:
    attachments_dir = get_attachments_dir(project_root)

    file_hash = compute_file_hash(content)
    storage_name = _dedupe_storage_filename(
        attachments_dir,
        _sanitize_storage_filename(filename),
    )

    file_path = attachments_dir / storage_name
    file_path.write_bytes(content)

    kind = _infer_kind_from_mime(mime_type)

    return {
        "filename": filename,
        "storage_name": storage_name,
        "storage_path": str(file_path),
        "url": build_attachment_url(storage_name),
        "mime_type": mime_type,
        "size": len(content),
        "hash": file_hash,
        "kind": kind,
    }


def resolve_attachment_path(project_root: Path, storage_name: str) -> Path:
    """
    根据存储名称解析附件路径
    
    Args:
        project_root: 项目根目录
        storage_name: 存储文件名
        
    Returns:
        附件文件路径
    """
    attachments_dir = get_attachments_dir(project_root)
    return attachments_dir / storage_name
