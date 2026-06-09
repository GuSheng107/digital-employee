from __future__ import annotations

import logging
import re
from datetime import datetime
from typing import Any

from app.memory_schema import (
    load_memory_file,
    save_memory_file,
    add_changelog_entry,
    MemoryItem,
    MemoryFile,
    load_timeline_file,
    save_timeline_file,
    load_document_memory,
    save_document_memory,
    list_timeline_months,
    MEMORY_JSON_FILES,
)

from memory_reviewer.schemas.patch import Patch

logger = logging.getLogger(__name__)

ALLOWED_TARGET_FILES: set[str] = set(MEMORY_JSON_FILES.keys())
_TIMELINE_MONTH_RE = re.compile(r"^\d{4}-\d{2}$")


def _explicit_item_fields(item: MemoryItem) -> set[str]:
    fields = getattr(item, "model_fields_set", None)
    if fields is None:
        fields = getattr(item, "__fields_set__", set())
    return {str(field) for field in fields}


def _apply_memory_item_update(item: MemoryItem, patch_item: MemoryItem) -> None:
    fields = _explicit_item_fields(patch_item)
    if "content" in fields:
        if str(patch_item.content or "").strip():
            item.content = patch_item.content
    if "content_type" in fields and patch_item.content_type:
        item.content_type = patch_item.content_type
    if "speed_lookup" in fields:
        item.speed_lookup = patch_item.speed_lookup
    if "retrieval" in fields:
        item.retrieval = patch_item.retrieval
    if "source" in fields and patch_item.source:
        item.source = patch_item.source
    if "source_id" in fields:
        item.source_id = patch_item.source_id
    if "priority" in fields:
        item.priority = patch_item.priority


def _is_safe_path_segment(value: str) -> bool:
    if not value or value in {".", ".."}:
        return False
    if "/" in value or "\\" in value or ":" in value:
        return False
    return True


def _normalize_target_file(target_file: str) -> str | None:
    value = str(target_file or "").strip().replace("\\", "/")
    if not value or value.startswith("/") or ":" in value:
        return None
    parts = [part for part in value.split("/") if part]
    if any(part in {".", ".."} for part in parts):
        return None
    if len(parts) == 1:
        key = parts[0]
        if key.endswith(".json"):
            key = key[:-5]
        if key in ALLOWED_TARGET_FILES:
            return key
        return None
    if len(parts) != 2:
        return None
    bucket, name = parts
    if name.endswith(".json"):
        name = name[:-5]
    if bucket == "timeline" and _TIMELINE_MONTH_RE.fullmatch(name):
        return f"timeline/{name}"
    if bucket == "documents" and _is_safe_path_segment(name):
        return f"documents/{name}"
    return None


def _load_patch_file(memory_root: str, target_file: str) -> MemoryFile:
    if target_file.startswith("timeline/") or target_file.startswith("timeline\\"):
        month = target_file.replace("\\", "/").split("/", 1)[1].replace(".json", "")
        tf = load_timeline_file(memory_root, month)
        return MemoryFile(file_key=f"timeline/{month}", items=tf.items, updated_at=tf.updated_at)
    if target_file.startswith("documents/") or target_file.startswith("documents\\"):
        source_id = target_file.replace("\\", "/").split("/", 1)[1].replace(".json", "")
        dm = load_document_memory(memory_root, source_id)
        return MemoryFile(file_key=f"documents/{source_id}", items=dm.items, updated_at=dm.updated_at)
    return load_memory_file(memory_root, target_file)


def _save_patch_file(memory_root: str, mf: MemoryFile) -> None:
    if mf.file_key.startswith("timeline/"):
        month = mf.file_key.split("/", 1)[1]
        tf = load_timeline_file(memory_root, month)
        tf.items = mf.items
        save_timeline_file(memory_root, tf)
        return
    if mf.file_key.startswith("documents/"):
        source_id = mf.file_key.split("/", 1)[1]
        dm = load_document_memory(memory_root, source_id)
        dm.items = mf.items
        save_document_memory(memory_root, dm)
        return
    save_memory_file(memory_root, mf)


def _build_new_item(patch: Patch) -> MemoryItem:
    ni = patch.new_item
    if ni is not None:
        return MemoryItem(
            content=ni.content,
            content_type=ni.content_type,
            speed_lookup=ni.speed_lookup,
            retrieval=ni.retrieval.model_dump() if hasattr(ni.retrieval, "model_dump") else ni.retrieval,
            source=ni.source,
            source_id=ni.source_id,
            priority=ni.priority,
        )
    return MemoryItem(
        content=patch.new_text or "",
    )


def apply_patch_plan(
    patches: list[Patch],
    memory_root: str,
    dry_run: bool = True,
) -> dict[str, list[str]]:
    results: dict[str, list[str]] = {
        "applied": [],
        "skipped": [],
        "errors": [],
    }

    for patch in patches:
        normalized_target_file = _normalize_target_file(patch.target_file)

        if not patch.target_file:
            results["skipped"].append(
                f"[skip] {patch.patch_id}: no target_file specified"
            )
            continue

        if normalized_target_file is None:
            results["errors"].append(
                f"[security] {patch.patch_id}: target_file blocked: {patch.target_file}"
            )
            continue

        patch = patch.model_copy(update={"target_file": normalized_target_file})

        if patch.action == "delete" and patch.target_file == "explicit":
            logger.warning("跳过删除显式记忆条目的补丁: patch_id=%s, item_id=%s", patch.patch_id, patch.item_id)
            results["skipped"].append(
                f"[skip] {patch.patch_id}: deleting explicit memory items is not allowed"
            )
            continue

        if dry_run:
            results["skipped"].append(
                f"[dry_run] {patch.patch_id}: {patch.action} on {patch.target_file} — {patch.reason}"
            )
            continue

        action = patch.action
        if action == "delete":
            _apply_delete(memory_root, patch, results)
        elif action == "update":
            _apply_update(memory_root, patch, results)
        elif action == "add":
            _apply_add(memory_root, patch, results)
        elif action == "merge":
            _apply_merge(memory_root, patch, results)
        elif action == "archive":
            _apply_archive(memory_root, patch, results)
        elif action == "promote":
            _apply_promote(memory_root, patch, results)
        elif action == "compress":
            _apply_compress(memory_root, patch, results)
        else:
            results["errors"].append(
                f"[error] {patch.patch_id}: unknown action {action}"
            )

    if not dry_run and results["applied"]:
        for applied_msg in results["applied"]:
            add_changelog_entry(
                memory_root,
                action="patch",
                target_file="",
                reason=applied_msg[:200],
            )

    return results


def _find_item_by_id(mf: MemoryFile, item_id: str) -> MemoryItem | None:
    for item in mf.items:
        if item.id == item_id:
            return item
    return None


def _apply_delete(memory_root: str, patch: Patch, results: dict[str, list[str]]) -> None:
    mf = _load_patch_file(memory_root, patch.target_file)
    item = _find_item_by_id(mf, patch.item_id) if patch.item_id else None
    if item is None:
        results["skipped"].append(
            f"[skip] {patch.patch_id}: item_id '{patch.item_id}' not found in {patch.target_file}"
        )
        return

    mf.items = [i for i in mf.items if i.id != patch.item_id]
    _save_patch_file(memory_root, mf)
    add_changelog_entry(
        memory_root,
        action="delete",
        target_file=patch.target_file,
        item_id=patch.item_id,
        item_content_preview=item.content[:100],
        reason=patch.reason,
    )
    results["applied"].append(f"[delete] {patch.patch_id}: removed item {patch.item_id} from {patch.target_file}")


def _apply_update(memory_root: str, patch: Patch, results: dict[str, list[str]]) -> None:
    mf = _load_patch_file(memory_root, patch.target_file)
    item = _find_item_by_id(mf, patch.item_id) if patch.item_id else None
    if item is None:
        results["skipped"].append(
            f"[skip] {patch.patch_id}: item_id '{patch.item_id}' not found in {patch.target_file}"
        )
        return

    if patch.new_item is not None:
        _apply_memory_item_update(item, patch.new_item)
        item.updated_at = datetime.now().isoformat(timespec="seconds")
    elif patch.new_text:
        item.content = patch.new_text
        item.updated_at = datetime.now().isoformat(timespec="seconds")

    _save_patch_file(memory_root, mf)
    add_changelog_entry(
        memory_root,
        action="update",
        target_file=patch.target_file,
        item_id=patch.item_id,
        item_content_preview=item.content[:100],
        reason=patch.reason,
    )
    results["applied"].append(f"[update] {patch.patch_id}: updated item {patch.item_id} in {patch.target_file}")


def _apply_add(memory_root: str, patch: Patch, results: dict[str, list[str]]) -> None:
    mf = _load_patch_file(memory_root, patch.target_file)
    new_item = _build_new_item(patch)
    mf.items.append(new_item)
    _save_patch_file(memory_root, mf)
    add_changelog_entry(
        memory_root,
        action="add",
        target_file=patch.target_file,
        item_id=new_item.id,
        item_content_preview=new_item.content[:100],
        reason=patch.reason,
    )
    results["applied"].append(f"[add] {patch.patch_id}: added item {new_item.id} to {patch.target_file}")


def _apply_merge(memory_root: str, patch: Patch, results: dict[str, list[str]]) -> None:
    mf = _load_patch_file(memory_root, patch.target_file)
    source_ids = patch.source_ids
    if not source_ids:
        results["skipped"].append(
            f"[skip] {patch.patch_id}: no source_ids for merge"
        )
        return

    found_items: list[MemoryItem] = []
    for sid in source_ids:
        item = _find_item_by_id(mf, sid)
        if item:
            found_items.append(item)

    if len(found_items) < len(source_ids):
        missing = set(source_ids) - {i.id for i in found_items}
        results["skipped"].append(
            f"[skip] {patch.patch_id}: source_ids not found: {missing}"
        )
        return

    new_item = _build_new_item(patch)
    mf.items = [i for i in mf.items if i.id not in source_ids]
    mf.items.append(new_item)
    _save_patch_file(memory_root, mf)
    add_changelog_entry(
        memory_root,
        action="merge",
        target_file=patch.target_file,
        item_id=new_item.id,
        item_content_preview=new_item.content[:100],
        reason=patch.reason,
    )
    results["applied"].append(
        f"[merge] {patch.patch_id}: merged {source_ids} into {new_item.id} in {patch.target_file}"
    )


def _apply_archive(memory_root: str, patch: Patch, results: dict[str, list[str]]) -> None:
    mf = _load_patch_file(memory_root, patch.target_file)
    item = _find_item_by_id(mf, patch.item_id) if patch.item_id else None
    if item is None:
        results["skipped"].append(
            f"[skip] {patch.patch_id}: item_id '{patch.item_id}' not found in {patch.target_file}"
        )
        return

    now = datetime.now()
    month_key = now.strftime("%Y-%m")
    tf = load_timeline_file(memory_root, month_key)
    archived_item = item.model_copy()
    archived_item.priority = min(archived_item.priority, 4.0)
    tf.items.append(archived_item)
    save_timeline_file(memory_root, tf)

    mf.items = [i for i in mf.items if i.id != patch.item_id]
    _save_patch_file(memory_root, mf)
    add_changelog_entry(
        memory_root,
        action="archive",
        target_file=patch.target_file,
        item_id=patch.item_id,
        item_content_preview=item.content[:100],
        reason=patch.reason,
    )
    results["applied"].append(
        f"[archive] {patch.patch_id}: archived item {patch.item_id} from {patch.target_file} to timeline/{month_key}"
    )


def _apply_promote(memory_root: str, patch: Patch, results: dict[str, list[str]]) -> None:
    source_file = patch.target_file
    target_file = patch.new_text or ""
    if not target_file:
        if patch.new_item and hasattr(patch.new_item, "content"):
            target_file = patch.new_item.content
    normalized_target_file = _normalize_target_file(target_file)
    if normalized_target_file is None:
        results["errors"].append(
            f"[error] {patch.patch_id}: invalid promote target: {target_file}"
        )
        return
    target_file = normalized_target_file

    src_mf = _load_patch_file(memory_root, source_file)
    item = _find_item_by_id(src_mf, patch.item_id) if patch.item_id else None
    if item is None:
        results["skipped"].append(
            f"[skip] {patch.patch_id}: item_id '{patch.item_id}' not found in {source_file}"
        )
        return

    promoted_item = item.model_copy()
    if patch.new_item:
        _apply_memory_item_update(promoted_item, patch.new_item)
    promoted_item.updated_at = datetime.now().isoformat(timespec="seconds")

    dst_mf = _load_patch_file(memory_root, target_file)
    dst_mf.items.append(promoted_item)
    _save_patch_file(memory_root, dst_mf)

    src_mf.items = [i for i in src_mf.items if i.id != patch.item_id]
    _save_patch_file(memory_root, src_mf)
    add_changelog_entry(
        memory_root,
        action="promote",
        target_file=f"{source_file} -> {target_file}",
        item_id=patch.item_id,
        item_content_preview=promoted_item.content[:100],
        reason=patch.reason,
    )
    results["applied"].append(
        f"[promote] {patch.patch_id}: promoted item {patch.item_id} from {source_file} to {target_file}"
    )


def _apply_compress(memory_root: str, patch: Patch, results: dict[str, list[str]]) -> None:
    mf = _load_patch_file(memory_root, patch.target_file)
    if patch.item_id:
        item = _find_item_by_id(mf, patch.item_id)
        if item is None:
            results["skipped"].append(
                f"[skip] {patch.patch_id}: item_id '{patch.item_id}' not found in {patch.target_file}"
            )
            return
        if patch.new_item:
            _apply_memory_item_update(item, patch.new_item)
            item.updated_at = datetime.now().isoformat(timespec="seconds")
        elif patch.new_text:
            item.content = patch.new_text
            item.updated_at = datetime.now().isoformat(timespec="seconds")
        _save_patch_file(memory_root, mf)
        add_changelog_entry(
            memory_root,
            action="compress",
            target_file=patch.target_file,
            item_id=patch.item_id,
            item_content_preview=item.content[:100],
            reason=patch.reason,
        )
        results["applied"].append(
            f"[compress] {patch.patch_id}: compressed item {patch.item_id} in {patch.target_file}"
        )
    elif patch.source_ids:
        found_items: list[MemoryItem] = []
        for sid in patch.source_ids:
            item = _find_item_by_id(mf, sid)
            if item:
                found_items.append(item)
        if not found_items:
            results["skipped"].append(
                f"[skip] {patch.patch_id}: no source_ids found for compress"
            )
            return
        new_item = _build_new_item(patch)
        mf.items = [i for i in mf.items if i.id not in patch.source_ids]
        mf.items.append(new_item)
        _save_patch_file(memory_root, mf)
        add_changelog_entry(
            memory_root,
            action="compress",
            target_file=patch.target_file,
            item_id=new_item.id,
            item_content_preview=new_item.content[:100],
            reason=patch.reason,
        )
        results["applied"].append(
            f"[compress] {patch.patch_id}: compressed {patch.source_ids} into {new_item.id} in {patch.target_file}"
        )
    else:
        results["skipped"].append(
            f"[skip] {patch.patch_id}: compress requires item_id or source_ids"
        )
