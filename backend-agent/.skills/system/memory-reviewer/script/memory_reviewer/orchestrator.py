from __future__ import annotations

import json
import logging
import re
from datetime import datetime
from pathlib import Path
from typing import Any

from langchain_core.language_models import BaseChatModel

from app.memory_schema import (
    load_memory_file,
    save_memory_file,
    add_changelog_entry,
    load_timeline_file,
    save_timeline_file,
    list_timeline_months,
    list_document_source_ids,
    load_document_memory,
    MemoryItem,
    MemoryFile,
    MEMORY_JSON_FILES,
    MEMORY_FILE_PRIORITIES,
    ContentType,
)
from memory_reviewer.chains.review_chain import run_review_chain
from memory_reviewer.chains.timeline_compaction_chain import run_timeline_compaction_chain
from memory_reviewer.chains.feedback_repair_chain import run_feedback_repair_chain
from memory_reviewer.chains.compress_chain import run_compress_chain
from memory_reviewer.chains.promote_chain import run_promote_chain
from memory_reviewer.patches.patch_applier import apply_patch_plan
from memory_reviewer.schemas.issue import Issue
from memory_reviewer.schemas.conflict import Conflict
from memory_reviewer.schemas.patch import Patch
from memory_reviewer.schemas.review_input import ReviewMetadata
from memory_reviewer.schemas.review_output import ReviewOutput

logger = logging.getLogger(__name__)

ALWAYS_READ_KEYS = [
    "rules",
    "explicit",
    "profile",
    "work",
    "inbox",
]


def load_memory_files(memory_root: str) -> dict[str, str]:
    files: dict[str, str] = {}

    for key in ALWAYS_READ_KEYS:
        mf = load_memory_file(memory_root, key)
        if mf.items:
            files[key] = mf.model_dump_json(indent=2, ensure_ascii=False)

    for month in list_timeline_months(memory_root):
        tf = load_timeline_file(memory_root, month)
        if tf.items:
            files[f"timeline/{month}"] = tf.model_dump_json(indent=2, ensure_ascii=False)

    for source_id in list_document_source_ids(memory_root):
        dm = load_document_memory(memory_root, source_id)
        if dm.items:
            files[f"documents/{source_id}"] = dm.model_dump_json(indent=2, ensure_ascii=False)

    return files


def _count_items_in_file(memory_root: str, file_key: str) -> int:
    mf = load_memory_file(memory_root, file_key)
    return len(mf.items)


def _compute_quality_score(issues: list[Issue], total_items: int) -> int:
    if total_items == 0:
        return 100
    penalty = 0
    for issue in issues:
        if issue.severity == "high":
            penalty += 15
        elif issue.severity == "medium":
            penalty += 8
        elif issue.severity == "low":
            penalty += 3
    return max(0, 100 - penalty)


def _is_safe_to_apply(patches: list[Patch]) -> bool:
    if not patches:
        return True
    return not any(p.requires_user_confirmation for p in patches)


def _patch_identity(patch: Patch) -> tuple[str, str, str, str]:
    return (
        str(patch.action or ""),
        str(patch.target_file or ""),
        str(patch.item_id or ""),
        "|".join(str(item) for item in (patch.source_ids or [])),
    )


def _dedupe_patches(existing: list[Patch], incoming: list[Patch]) -> list[Patch]:
    seen = {_patch_identity(patch) for patch in existing}
    unique: list[Patch] = []
    for patch in incoming:
        identity = _patch_identity(patch)
        if identity in seen:
            continue
        seen.add(identity)
        unique.append(patch)
    return unique


def _patch_report_entry(patch: Patch) -> dict[str, Any]:
    return {
        "patch_id": patch.patch_id,
        "action": patch.action,
        "target_file": patch.target_file,
        "item_id": patch.item_id,
        "item_content": str(patch.new_item.content or "").strip() if patch.new_item else str(patch.old_text or "").strip(),
        "reason": patch.reason,
    }


def _patch_id_from_result_message(message: str) -> str:
    prefix = str(message or "").split(":", 1)[0].strip()
    if not prefix:
        return ""
    parts = prefix.split()
    return parts[-1] if parts else ""


def _patches_applied_for_report(
    patches: list[Patch],
    patch_results: dict[str, list[str]] | None,
) -> list[dict[str, Any]]:
    applied_ids = {
        patch_id
        for patch_id in (
            _patch_id_from_result_message(message)
            for message in (patch_results or {}).get("applied", [])
        )
        if patch_id
    }
    return [_patch_report_entry(patch) for patch in patches if patch.patch_id in applied_ids]


def _build_changelog_items(
    issues: list[Issue],
    patches: list[Patch],
) -> list[str]:
    items: list[str] = []
    for issue in issues:
        items.append(f"[{issue.severity}] {issue.category}: {issue.description}")
    for patch in patches:
        items.append(f"[patch] {patch.action} on {patch.target_file}: {patch.reason}")
    return items


def _raw_patch_to_patch(raw_patch: dict, prefix: str = "p", counter: int = 0) -> Patch:
    new_item = None
    ni = raw_patch.get("new_item")
    if ni and isinstance(ni, dict):
        item_data: dict[str, Any] = {}
        if "content" in ni:
            item_data["content"] = ni.get("content", "")
        if "content_type" in ni:
            ct = ni.get("content_type", "fact")
            item_data["content_type"] = ct if ct in ContentType.__args__ else "fact"
        if "speed_lookup" in ni:
            item_data["speed_lookup"] = ni.get("speed_lookup", "")
        if "retrieval" in ni:
            item_data["retrieval"] = ni.get("retrieval", {})
        for field in ("source", "source_id", "priority"):
            if field in ni:
                item_data[field] = ni.get(field)
        new_item = MemoryItem(**item_data)

    return Patch(
        patch_id=raw_patch.get("patch_id", f"{prefix}-{counter}"),
        target_file=raw_patch.get("target_file", ""),
        action=raw_patch.get("action", "update"),
        target_section=raw_patch.get("target_section", ""),
        item_id=raw_patch.get("item_id", ""),
        source_ids=raw_patch.get("source_ids", []),
        old_text=raw_patch.get("old_text", ""),
        new_text=raw_patch.get("new_text", ""),
        new_item=new_item,
        reason=raw_patch.get("reason", ""),
        confidence=raw_patch.get("confidence", "medium"),
        requires_user_confirmation=raw_patch.get("requires_user_confirmation", False),
    )


def _raw_issue_to_issue(
    raw_issue: Any,
    *,
    default_category: str = "missing_memory",
    default_severity: str = "medium",
) -> Issue:
    if isinstance(raw_issue, dict):
        try:
            return Issue(**raw_issue)
        except Exception:
            description = json.dumps(raw_issue, ensure_ascii=False)
    else:
        description = str(raw_issue)
    return Issue(
        category=default_category,
        severity=default_severity,
        description=description,
    )


def _merge_token_usage(target: dict[str, int], incoming: dict[str, Any]) -> None:
    for key in ("input_tokens", "output_tokens", "total_tokens"):
        try:
            value = int(incoming.get(key, 0) or 0)
        except (TypeError, ValueError):
            value = 0
        if value:
            target[key] = int(target.get(key, 0) or 0) + value


def _feedback_review_text(sample: dict[str, Any], feedback_reason: str) -> str:
    parts = ["用户将该回复标记为无用。"]
    if feedback_reason:
        parts.append(f"反馈原因: {feedback_reason}")
    note = str(sample.get("feedback_note") or "").strip()
    if note:
        parts.append(note)
    parts.append("请优先判断是否存在记忆缺失、错误记忆、召回失败、速查词问题或无关注入，并生成可修复补丁。")
    return "\n".join(parts)


def review_memory_files(
    memory_root: str = ".memory",
    metadata: dict[str, Any] | None = None,
    llm: BaseChatModel | None = None,
    skip_report: bool = False,
) -> dict[str, Any]:
    if metadata is None:
        metadata = {}
    metadata.setdefault("memory_root", memory_root)
    meta = ReviewMetadata(**metadata)

    memory_files = load_memory_files(meta.memory_root)

    all_issues: list[Issue] = []
    all_conflicts: list[Conflict] = []
    llm_token_usage: dict[str, int] = {}

    llm_result: dict[str, Any] = {}
    llm_error = ""
    if llm is not None:
        try:
            llm_result = run_review_chain(
                review_type="memory_files",
                memory_files=memory_files,
                llm=llm,
            )
            llm_token_usage = dict(llm_result.get("token_usage", {}) or {})
            llm_error = str(llm_result.get("llm_error", "") or "").strip()
            for issue_data in llm_result.get("issues", []):
                all_issues.append(
                    _raw_issue_to_issue(
                        issue_data,
                        default_category="low_value",
                        default_severity="low",
                    )
                )
            for conflict_data in llm_result.get("conflicts", []):
                if isinstance(conflict_data, dict):
                    all_conflicts.append(Conflict(**conflict_data))
        except Exception as exc:
            logger.warning("LLM review chain failed: %s", exc)
            llm_error = str(exc)

    priority_issues, priority_patches = _check_cross_file_priority(meta.memory_root)
    all_issues.extend(priority_issues)

    missing_warnings: list[str] = []
    for key in ["explicit", "profile"]:
        mf = load_memory_file(meta.memory_root, key)
        if not mf.items:
            missing_warnings.append(f"{key} 为空或缺失")

    total_items = 0
    for key in ALWAYS_READ_KEYS:
        total_items += _count_items_in_file(meta.memory_root, key)

    quality_score = _compute_quality_score(all_issues, total_items)

    patches: list[Patch] = []
    patch_id = 0
    for raw_patch in llm_result.get("recommended_patches", []):
        patch_id += 1
        if isinstance(raw_patch, dict):
            patches.append(_raw_patch_to_patch(raw_patch, prefix="p", counter=patch_id))
    patches.extend(_dedupe_patches(patches, priority_patches))

    changelog_items = _build_changelog_items(all_issues, patches)

    summary_parts: list[str] = []
    if all_issues:
        high = sum(1 for i in all_issues if i.severity == "high")
        medium = sum(1 for i in all_issues if i.severity == "medium")
        low = sum(1 for i in all_issues if i.severity == "low")
        summary_parts.append(f"发现 {len(all_issues)} 个问题: {high} 高、{medium} 中、{low} 低")
    else:
        summary_parts.append("未发现问题")
    if all_conflicts:
        summary_parts.append(f"发现 {len(all_conflicts)} 个冲突")
    if missing_warnings:
        summary_parts.append(f"缺失警告: {', '.join(missing_warnings)}")
    if llm_error:
        summary_parts.append(f"LLM 审核失败: {llm_error[:300]}")

    compress_suggestions = llm_result.get("compress_suggestions", [])
    promote_suggestions = llm_result.get("promote_suggestions", [])

    output = ReviewOutput(
        review_summary="；".join(summary_parts),
        quality_score=quality_score,
        issues=all_issues,
        recommended_patches=patches,
        compress_suggestions=compress_suggestions,
        promote_suggestions=promote_suggestions,
        items_to_merge=[p.patch_id for p in patches if p.action == "merge"],
        items_to_delete=[p.patch_id for p in patches if p.action == "delete"],
        items_to_deprecate=[p.patch_id for p in patches if p.action == "deprecate"],
        items_to_move_to_inbox=[p.patch_id for p in patches if p.action == "promote"],
        items_to_compress=[p.patch_id for p in patches if p.action == "compress"],
        missing_memory_warnings=missing_warnings,
        conflicts=all_conflicts,
        changelog_items=changelog_items,
        safe_to_apply=_is_safe_to_apply(patches),
        token_usage=llm_token_usage,
    )

    patch_results: dict[str, list[str]] | None = None
    if not skip_report:
        if meta.mode == "patch" and patches:
            patch_results = apply_patch_plan(patches, meta.memory_root, dry_run=False)
        elif meta.mode == "dry_run":
            patch_results = apply_patch_plan(patches, meta.memory_root, dry_run=True)

    file_item_counts: dict[str, int] = {}
    for key in ALWAYS_READ_KEYS:
        item_count = _count_items_in_file(meta.memory_root, key)
        file_item_counts[key] = item_count

    boundary_metrics = {
        "avg_token_usage_rate": 0.0,
        "miss_rate": 0.0,
        "irrelevant_injection_rate": 0.0,
        "file_item_counts": file_item_counts,
    }
    output.boundary_metrics = boundary_metrics

    if not skip_report:
        patches_applied_for_report = _patches_applied_for_report(patches, patch_results)

        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        _write_review_report(
            meta.memory_root,
            report_name=f"memory_files_review_{timestamp}.md",
            title="记忆文件审核",
            summary=output.review_summary,
            counters={
                "used_effectively": total_items,
                "used_but_wasteful": 0,
                "needed_but_missed": len(missing_warnings),
                "irrelevant_injection": 0,
            },
            suspicious_samples=[],
            issues=all_issues,
            patches_applied=patches_applied_for_report,
            patch_results=patch_results,
            boundary_metrics=boundary_metrics,
            token_usage=llm_token_usage,
            review_prompt=str(metadata.get("review_prompt", "") or ""),
            review_traces=[llm_result["llm_review_trace"]] if isinstance(llm_result.get("llm_review_trace"), dict) else [],
        )

    output_data = output.model_dump()
    if isinstance(llm_result.get("llm_review_trace"), dict):
        output_data["llm_review_trace"] = llm_result["llm_review_trace"]
    output_data["ok"] = not bool(llm_error)
    if llm_error:
        output_data["llm_error"] = llm_error
        output_data["error"] = f"LLM 审核失败: {llm_error}"
    if patch_results is not None:
        output_data["patch_results"] = patch_results
    return output_data


def review_memory_pack(
    memory_pack: str,
    current_message: str = "",
    agent_answer: str = "",
    memory_files: dict[str, str] | None = None,
    metadata: dict[str, Any] | None = None,
    llm: BaseChatModel | None = None,
) -> dict[str, Any]:
    if metadata is None:
        metadata = {}
    meta = ReviewMetadata(**metadata)
    if memory_files is None:
        memory_files = load_memory_files(meta.memory_root)

    llm_result = {}
    if llm is not None:
        try:
            llm_result = run_review_chain(
                review_type="memory_pack",
                memory_files=memory_files,
                current_message=current_message,
                agent_answer=agent_answer,
                memory_pack=memory_pack,
                llm=llm,
            )
        except Exception as exc:
            logger.warning("LLM memory pack review failed: %s", exc)
            llm_result = {}

    pack_issues: list[Issue] = []
    for issue_data in llm_result.get("issues", []):
        pack_issues.append(
            _raw_issue_to_issue(
                issue_data,
                default_category="low_value",
                default_severity="low",
            )
        )

    missing_warnings: list[str] = []
    has_explicit_pack_content = (
        "explicit" in memory_pack.lower()
        or "管理员配置内容" in memory_pack
        or "来源：管理员配置内容" in memory_pack
    )
    if not has_explicit_pack_content:
        mf = load_memory_file(meta.memory_root, "explicit")
        if mf.items:
            missing_warnings.append("记忆包缺少显式记忆")

    quality_score = _compute_quality_score(pack_issues, len(memory_pack.splitlines()))

    patches: list[Patch] = []
    patch_id = 0
    for raw_patch in llm_result.get("recommended_patches", []):
        patch_id += 1
        if isinstance(raw_patch, dict):
            patches.append(_raw_patch_to_patch(raw_patch, prefix="pack-p", counter=patch_id))

    summary_parts: list[str] = []
    if pack_issues:
        summary_parts.append(f"记忆包审核发现 {len(pack_issues)} 个问题")
    else:
        summary_parts.append("记忆包审核通过")
    if missing_warnings:
        summary_parts.append(f"缺失警告: {', '.join(missing_warnings)}")

    changelog_items = _build_changelog_items(pack_issues, patches)

    compress_suggestions = llm_result.get("compress_suggestions", [])
    promote_suggestions = llm_result.get("promote_suggestions", [])

    output = ReviewOutput(
        review_summary="；".join(summary_parts),
        quality_score=quality_score,
        issues=pack_issues,
        recommended_patches=patches,
        compress_suggestions=compress_suggestions,
        promote_suggestions=promote_suggestions,
        items_to_merge=[],
        items_to_delete=[],
        items_to_deprecate=[],
        items_to_move_to_inbox=[],
        items_to_compress=[p.patch_id for p in patches if p.action == "compress"],
        missing_memory_warnings=missing_warnings,
        conflicts=[],
        changelog_items=changelog_items,
        safe_to_apply=_is_safe_to_apply(patches),
        token_usage=dict(llm_result.get("token_usage", {}) or {}),
    )

    output_data = output.model_dump()
    if isinstance(llm_result.get("llm_review_trace"), dict):
        output_data["llm_review_trace"] = llm_result["llm_review_trace"]
    llm_error = str(llm_result.get("llm_error") or llm_result.get("error") or "").strip()
    output_data["ok"] = not bool(llm_error)
    if llm_error:
        output_data["llm_error"] = llm_error
        output_data["error"] = f"LLM 审核失败: {llm_error}"
    return output_data


def handle_user_feedback(
    user_feedback: str,
    memory_files: dict[str, str] | None = None,
    metadata: dict[str, Any] | None = None,
    llm: BaseChatModel | None = None,
) -> dict[str, Any]:
    if metadata is None:
        metadata = {}
    meta = ReviewMetadata(**metadata)
    if memory_files is None:
        memory_files = load_memory_files(meta.memory_root)

    repair_result = run_feedback_repair_chain(
        user_feedback=user_feedback,
        memory_files=memory_files,
        current_message="",
        llm=llm,
    )

    patches: list[Patch] = []
    patch_id = 0
    for raw_patch in repair_result.get("recommended_patches", []):
        patch_id += 1
        if isinstance(raw_patch, dict):
            patches.append(_raw_patch_to_patch(raw_patch, prefix="feedback-p", counter=patch_id))

    items_to_delete = repair_result.get("items_to_delete", [])
    items_to_move = repair_result.get("items_to_move_to_inbox", [])
    changelog_items = repair_result.get("changelog_items", [])

    summary = f"用户反馈处理: {user_feedback[:100]}"
    if patches:
        summary += f"；生成 {len(patches)} 个补丁建议"

    quality_score = 50 if patches else 100

    output = ReviewOutput(
        review_summary=summary,
        quality_score=quality_score,
        issues=[],
        recommended_patches=patches,
        compress_suggestions=[],
        promote_suggestions=[],
        items_to_merge=[],
        items_to_delete=items_to_delete,
        items_to_deprecate=[],
        items_to_move_to_inbox=items_to_move,
        items_to_compress=[],
        missing_memory_warnings=[],
        conflicts=[],
        changelog_items=changelog_items,
        safe_to_apply=_is_safe_to_apply(patches),
        token_usage=dict(repair_result.get("token_usage", {}) or {}),
    )

    if meta.mode == "patch" and patches:
        apply_patch_plan(patches, meta.memory_root, dry_run=False)
    elif meta.mode == "dry_run":
        apply_patch_plan(patches, meta.memory_root, dry_run=True)

    output_data = output.model_dump()
    llm_error = str(repair_result.get("llm_error") or repair_result.get("error") or "").strip()
    output_data["ok"] = not bool(llm_error)
    if llm_error:
        output_data["llm_error"] = llm_error
        output_data["error"] = f"反馈修复 LLM 失败: {llm_error}"
    return output_data


def compress_memory_file(
    file_key: str,
    memory_root: str = ".memory",
    llm: BaseChatModel | None = None,
) -> dict[str, Any]:
    mf = load_memory_file(memory_root, file_key)
    if not mf.items:
        return {"file_key": file_key, "compressions_applied": 0, "status": "empty"}

    items_before = len(mf.items)

    result = run_compress_chain(llm=llm, file_key=file_key, items=mf.items)
    if result.llm_error:
        return {
            "file_key": file_key,
            "compressions_applied": 0,
            "status": "failed",
            "error": result.llm_error,
            "token_usage": result.token_usage,
        }

    applied = 0
    patches: list[Patch] = []
    for comp in result.compressions:
        action = comp.action if comp.action in ("merge", "archive", "delete") else "compress"
        patch = Patch(
            patch_id=f"comp-{applied + 1}",
            target_file=file_key,
            action=action,
            item_id=comp.source_ids[0] if len(comp.source_ids) == 1 else "",
            source_ids=comp.source_ids,
            new_item=comp.new_item,
            reason=comp.reason,
            confidence="medium",
            requires_user_confirmation=True,
        )
        patches.append(patch)
        applied += 1

    if patches:
        patch_results = apply_patch_plan(patches, memory_root, dry_run=False)
        mf_after = load_memory_file(memory_root, file_key)
        items_after = len(mf_after.items)
        patches_applied_for_report = [
            {
                "patch_id": p.patch_id,
                "action": p.action,
                "target_file": p.target_file,
                "item_id": p.item_id,
                "item_content": str(p.new_item.content or "").strip() if p.new_item else str(p.old_text or "").strip(),
                "reason": p.reason,
            }
            for p in patches
        ]
        boundary_metrics = {
            "avg_token_usage_rate": 0.0,
            "miss_rate": 0.0,
            "irrelevant_injection_rate": 0.0,
            "file_item_counts": {
                file_key: items_after,
                f"{file_key}_before": items_before,
            },
        }
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        _write_review_report(
            memory_root,
            report_name=f"compress_{file_key}_{timestamp}.md",
            title=f"压缩审核：{file_key}",
            summary=f"已压缩 {file_key}: {items_before} -> {items_after} 条，应用 {applied} 个压缩补丁",
            counters={
                "used_effectively": items_after,
                "used_but_wasteful": 0,
                "needed_but_missed": 0,
                "irrelevant_injection": 0,
            },
            suspicious_samples=[],
            issues=[],
            patches_applied=patches_applied_for_report,
            boundary_metrics=boundary_metrics,
        )
        return {
            "file_key": file_key,
            "compressions_applied": applied,
            "status": "applied",
            "patch_results": patch_results,
            "token_usage": result.token_usage,
        }

    return {
        "file_key": file_key,
        "compressions_applied": 0,
        "status": "no_compressions_needed",
        "token_usage": result.token_usage,
    }


def promote_inbox_items(
    memory_root: str = ".memory",
    llm: BaseChatModel | None = None,
) -> dict[str, Any]:
    mf = load_memory_file(memory_root, "inbox")
    if not mf.items:
        return {"promoted": 0, "status": "inbox_empty"}

    items_before = len(mf.items)

    result = run_promote_chain(llm=llm, items=mf.items)
    if result.llm_error:
        return {
            "promoted": 0,
            "status": "failed",
            "error": result.llm_error,
            "token_usage": result.token_usage,
        }

    promoted = 0
    patches: list[Patch] = []
    for promo in result.promotions:
        patch = Patch(
            patch_id=f"promo-{promoted + 1}",
            target_file="inbox",
            action="promote",
            item_id=promo.item_id,
            new_text=promo.target_file,
            new_item=MemoryItem(
                content_type=promo.content_type,
                priority=promo.priority,
            ),
            reason=promo.reason,
            confidence="medium",
            requires_user_confirmation=True,
        )
        patches.append(patch)
        promoted += 1

    if patches:
        patch_results = apply_patch_plan(patches, memory_root, dry_run=False)
        mf_after = load_memory_file(memory_root, "inbox")
        items_after = len(mf_after.items)
        patches_applied_for_report = [
            {
                "patch_id": p.patch_id,
                "action": p.action,
                "target_file": p.target_file,
                "item_id": p.item_id,
                "item_content": str(p.new_item.content or "").strip() if p.new_item else str(p.old_text or "").strip(),
                "reason": p.reason,
            }
            for p in patches
        ]
        boundary_metrics = {
            "avg_token_usage_rate": 0.0,
            "miss_rate": 0.0,
            "irrelevant_injection_rate": 0.0,
            "file_item_counts": {
                "inbox": items_after,
                "inbox_before": items_before,
            },
        }
        timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
        _write_review_report(
            memory_root,
            report_name=f"promote_inbox_{timestamp}.md",
            title="收件箱提升审核",
            summary=f"已从收件箱提升 {promoted} 条记忆：{items_before} -> {items_after} 条剩余",
            counters={
                "used_effectively": promoted,
                "used_but_wasteful": 0,
                "needed_but_missed": 0,
                "irrelevant_injection": 0,
            },
            suspicious_samples=[],
            issues=[],
            patches_applied=patches_applied_for_report,
            boundary_metrics=boundary_metrics,
        )
        return {
            "promoted": promoted,
            "status": "applied",
            "patch_results": patch_results,
            "token_usage": result.token_usage,
        }

    return {
        "promoted": 0,
        "status": "no_promotions_needed",
        "token_usage": result.token_usage,
    }


def compact_timeline(
    memory_root: str = ".memory",
    metadata: dict[str, Any] | None = None,
    llm: BaseChatModel | None = None,
) -> dict[str, Any]:
    if metadata is None:
        metadata = {}
    meta = ReviewMetadata(**metadata)

    months = list_timeline_months(memory_root)
    if not months:
        return {"status": "no_timeline_files"}

    all_results: list[dict[str, Any]] = []
    token_usage: dict[str, int] = {}
    llm_errors: list[str] = []
    for month in months:
        tf = load_timeline_file(memory_root, month)
        if not tf.items:
            continue

        timeline_text = tf.model_dump_json(indent=2, ensure_ascii=False)

        result = run_timeline_compaction_chain(
            timeline_text=timeline_text,
            current_date=meta.current_date,
            llm=llm,
        )
        _merge_token_usage(token_usage, dict(result.get("token_usage", {}) or {}))
        llm_error = str(result.get("llm_error") or result.get("error") or "").strip()
        if llm_error:
            llm_errors.append(f"{month}: {llm_error}")

        compacted_text = result.get("compacted_text", "")
        if compacted_text and compacted_text != timeline_text:
            try:
                data = json.loads(compacted_text)
                data.setdefault("month", month)
                data.setdefault("version", 1)
                new_tf = type(tf).model_validate(data)
                new_tf.month = month
                save_timeline_file(memory_root, new_tf)
            except Exception as exc:
                logger.warning("Failed to parse compacted timeline for %s: %s", month, exc)

        all_results.append({
            "month": month,
            "removed_items": result.get("removed_items", []),
            "merged_items": result.get("merged_items", []),
            "preserved_items": result.get("preserved_items", []),
            "token_savings_estimate": result.get("token_savings_estimate", 0),
            "llm_error": llm_error,
        })

    return {
        "status": "completed_with_errors" if llm_errors else "completed",
        "months_processed": all_results,
        "token_usage": token_usage,
        "llm_errors": llm_errors,
    }


def _truncate_text(text: str, limit: int = 500) -> str:
    value = str(text or "").strip()
    if len(value) <= limit:
        return value
    return value[: limit - 3].rstrip() + "..."


def _normalize_duplicate_text(text: str) -> str:
    value = str(text or "").lower()
    value = re.sub(r"(问题|答案|原因|解决|事实|术语|查询词|来源|记忆|内容)[:：]", "", value)
    return re.sub(r"[\s,，。.!！?？:：;；|｜/\\()\[\]{}<>《》\"'`_-]+", "", value)


def _text_similarity(a: str, b: str) -> float:
    a_set = set(a[i:i + 2] for i in range(len(a) - 1))
    b_set = set(b[i:i + 2] for i in range(len(b) - 1))
    if not a_set and not b_set:
        return 1.0
    if not a_set or not b_set:
        return 0.0
    return len(a_set & b_set) / len(a_set | b_set)


def _is_duplicate_content(a: str, b: str) -> bool:
    left = _normalize_duplicate_text(a)
    right = _normalize_duplicate_text(b)
    if not left or not right:
        return False
    if left == right:
        return True
    shorter = min(len(left), len(right))
    if shorter >= 18 and (left in right or right in left):
        return True
    return _text_similarity(left, right) >= 0.86


def _memory_priority_tier(file_key: str, item: MemoryItem) -> int:
    if file_key == "explicit" or str(item.source or "") == "explicit":
        return 3
    if file_key.startswith("documents/") or str(item.source or "") == "document":
        return 2
    return 1


def _iter_review_items(memory_root: str) -> list[tuple[str, MemoryItem, int]]:
    review_items: list[tuple[str, MemoryItem, int]] = []
    for key in ("explicit", "work", "profile", "inbox"):
        mf = load_memory_file(memory_root, key)
        for item in mf.items:
            review_items.append((key, item, _memory_priority_tier(key, item)))
    for source_id in list_document_source_ids(memory_root):
        key = f"documents/{source_id}"
        dm = load_document_memory(memory_root, source_id)
        for item in dm.items:
            review_items.append((key, item, _memory_priority_tier(key, item)))
    for month in list_timeline_months(memory_root):
        key = f"timeline/{month}"
        tf = load_timeline_file(memory_root, month)
        for item in tf.items:
            review_items.append((key, item, _memory_priority_tier(key, item)))
    return review_items


def _check_cross_file_priority(memory_root: str) -> tuple[list[Issue], list[Patch]]:
    review_items = _iter_review_items(memory_root)
    issues: list[Issue] = []
    patches: list[Patch] = []
    patch_counter = 0
    seen_delete_ids: set[tuple[str, str]] = set()
    tier_labels = {
        3: "显式记忆",
        2: "文档记忆",
        1: "会话记忆",
    }

    for low_file, low_item, low_tier in review_items:
        low_id = str(low_item.id or "")
        if not low_id:
            continue
        if (low_file, low_id) in seen_delete_ids:
            continue
        low_content = str(low_item.content or "")
        if not low_content.strip():
            continue

        for high_file, high_item, high_tier in review_items:
            if high_tier <= low_tier:
                continue
            if low_file == high_file and str(low_item.id or "") == str(high_item.id or ""):
                continue
            if not _is_duplicate_content(low_content, str(high_item.content or "")):
                continue

            patch_counter += 1
            seen_delete_ids.add((low_file, low_id))
            high_label = tier_labels.get(high_tier, high_file)
            low_label = tier_labels.get(low_tier, low_file)
            issues.append(Issue(
                issue_id=f"priority-dup-{patch_counter}",
                severity="medium",
                category="duplicate",
                description=f"{low_file} 条目与 {high_file} 内容重复（优先级：{high_label} > {low_label}）",
                affected_files=[low_file, high_file],
            ))
            patches.append(Patch(
                patch_id=f"p-pri-{patch_counter}",
                action="delete",
                target_file=low_file,
                item_id=low_id,
                reason=f"与 {high_file} 条目重复，按优先级 {high_label} > {low_label} 保留高优先级记忆",
                confidence="high",
                requires_user_confirmation=False,
            ))
            break

    return issues, patches


def _review_sample_issue_text(sample: dict[str, Any]) -> str:
    issue_parts: list[str] = []
    for issue in sample.get("sample_issues", []) or []:
        if isinstance(issue, dict):
            severity = str(issue.get("severity") or "").strip()
            category = str(issue.get("category") or "").strip()
            description = str(issue.get("description") or "").strip()
            label = "/".join(part for part in (severity, category) if part)
            issue_parts.append(f"{label}: {description}" if label else description)
        else:
            text = str(issue or "").strip()
            if text:
                issue_parts.append(text)
    return "；".join(part for part in issue_parts if part)


def _review_sample_detail(
    sample: dict[str, Any],
    *,
    status: str,
    selected_files: list[str],
    budget_used: int,
    needs_more_memory: bool,
    final_answer: str,
    memory_pack: str,
    feedback_id: str,
    feedback_result: str,
    feedback_reason: str,
    sample_issues: list[Issue],
) -> dict[str, Any]:
    return {
        "trace_id": str(sample.get("trace_id", "")),
        "call_type": str(sample.get("call_type", "")),
        "status": status,
        "selected_files": selected_files,
        "selected_sections": [str(s) for s in sample.get("selected_sections", [])],
        "token_budget_used_estimate": budget_used,
        "input_tokens": int(sample.get("input_tokens", 0) or 0),
        "output_tokens": int(sample.get("output_tokens", 0) or 0),
        "total_tokens": int(sample.get("total_tokens", 0) or 0),
        "confidence": str(sample.get("confidence", "")),
        "needs_more_memory": needs_more_memory,
        "user_query": str(sample.get("user_query", "")),
        "final_answer": final_answer,
        "memory_pack": memory_pack,
        "chat_id": str(sample.get("chat_id", "")),
        "chat_display_name": str(sample.get("chat_display_name", "")),
        "bot_key": str(sample.get("bot_key", "")),
        "bot_name": str(sample.get("bot_name", "")),
        "feedback_id": feedback_id,
        "feedback_result": feedback_result,
        "feedback_reason": feedback_reason,
        "feedback_created_at": str(sample.get("feedback_created_at", "")),
        "feedback_user_id": str(sample.get("feedback_user_id", "")),
        "feedback_msg_id": str(sample.get("feedback_msg_id", "")),
        "sample_issues": [issue.model_dump() for issue in sample_issues],
    }


def _append_review_sample_lines(
    lines: list[str],
    sample: dict[str, Any],
    *,
    answer_limit: int = 2000,
    memory_pack_limit: int = 500,
) -> None:
    selected_files = [str(item) for item in sample.get("selected_files", [])]
    selected_sections = [str(item) for item in sample.get("selected_sections", [])]
    issue_text = _review_sample_issue_text(sample)
    lines.extend(
        [
            f"### {sample.get('trace_id', '')}",
            f"- 调用类型: {sample.get('call_type', '')}",
            f"- 状态: {sample.get('status', '')}",
            f"- 选中文件: {', '.join(selected_files) or '-'}",
            f"- token 预算估算: {sample.get('token_budget_used_estimate', 0)}",
            (
                f"- 实际 token: input={sample.get('input_tokens', 0)}, "
                f"output={sample.get('output_tokens', 0)}, total={sample.get('total_tokens', 0)}"
            ),
            f"- 置信度: {sample.get('confidence', '')}",
            f"- 会话: {sample.get('chat_display_name', '') or sample.get('chat_id', '')}",
            f"- Bot: {sample.get('bot_name', '') or sample.get('bot_key', '')}",
            f"- 用户反馈: {sample.get('feedback_result', '-') or '-'} {sample.get('feedback_created_at', '')}",
            f"- 反馈原因: {_truncate_text(sample.get('feedback_reason', ''), 240) or '-'}",
            f"- 是否需要更多记忆: {'是' if bool(sample.get('needs_more_memory', False)) else '否'}",
            f"- 样本问题: {_truncate_text(issue_text, 500) or '-'}",
            f"- 用户问题: {_truncate_text(sample.get('user_query', ''), 240)}",
            f"- Agent 最终回答: {_truncate_text(sample.get('final_answer', ''), answer_limit) or '-'}",
            f"- 记忆包摘要: {_truncate_text(sample.get('memory_pack', ''), memory_pack_limit) or '-'}",
            f"- 选中段落: {', '.join(selected_sections) or '-'}",
            "",
        ]
    )


def _write_review_report(
    memory_root: str,
    *,
    report_name: str,
    title: str,
    summary: str,
    counters: dict[str, int],
    suspicious_samples: list[dict[str, Any]],
    issues: list[Issue],
    reviewed_samples: list[dict[str, Any]] | None = None,
    patches_applied: list[dict] | None = None,
    patch_results: dict[str, list[str]] | None = None,
    boundary_metrics: dict | None = None,
    token_usage: dict[str, int] | None = None,
    review_prompt: str = "",
    review_traces: list[dict[str, Any]] | None = None,
) -> str:
    reviews_dir = Path(memory_root) / "reviews"
    reviews_dir.mkdir(parents=True, exist_ok=True)
    report_path = reviews_dir / report_name
    severity_labels = {"high": "高", "medium": "中", "low": "低", "info": "信息"}
    category_labels = {
        "duplicate": "重复记忆",
        "conflict": "冲突记忆",
        "outdated": "过期记忆",
        "wrong_promotion": "放置位置不当",
        "excessive_length": "冗长/重复",
        "missing_memory": "缺失记忆",
        "low_value": "低价值记忆",
        "token_over_budget": "超过 token 预算",
        "chinese_not_preserved": "中文未保留",
        "bad_speed_lookup": "速查词质量问题",
        "fragmented_memory": "记忆碎片化",
        "used_effectively": "有效使用",
    }
    action_labels = {
        "add": "新增",
        "update": "更新",
        "delete": "删除",
        "merge": "合并",
        "compress": "压缩",
        "promote": "提升",
        "archive": "归档",
    }
    lines = [
        f"# {title}",
        "",
        f"- 生成时间: {datetime.now().isoformat(timespec='seconds')}",
        f"- 摘要: {summary}",
        f"- 有效使用: {counters.get('used_effectively', 0)}",
        f"- 使用但浪费: {counters.get('used_but_wasteful', 0)}",
        f"- 需要但未命中: {counters.get('needed_but_missed', 0)}",
        f"- 无关注入: {counters.get('irrelevant_injection', 0)}",
        f"- 用户标记无用: {counters.get('feedback_useless', 0)}",
        f"- 用户标记有用: {counters.get('feedback_useful', 0)}",
    ]
    if token_usage:
        lines.append(
            f"- LLM token: input={int(token_usage.get('input_tokens', 0) or 0)}, "
            f"output={int(token_usage.get('output_tokens', 0) or 0)}, "
            f"total={int(token_usage.get('total_tokens', 0) or 0)}"
        )
    lines.extend([
        "",
        "## 审核过程",
        "",
        "- 说明: 报告记录可观测证据，包括审核指令、LLM 回复预览、解析结果、记忆包、Agent 最终回答与用户反馈；未记录的模型内部推理不会被补造。",
        f"- 审核指令: {_truncate_text(review_prompt, 2000) or '-'}",
        "",
    ])
    if review_traces:
        for index, trace in enumerate(review_traces[:10], 1):
            trace_usage = trace.get("token_usage", {}) if isinstance(trace.get("token_usage", {}), dict) else {}
            lines.extend([
                f"### LLM 调用 {index}",
                f"- 类型: {trace.get('review_type', '')}",
                (
                    f"- token: input={int(trace_usage.get('input_tokens', 0) or 0)}, "
                    f"output={int(trace_usage.get('output_tokens', 0) or 0)}, "
                    f"total={int(trace_usage.get('total_tokens', 0) or 0)}"
                ),
                f"- 错误: {_truncate_text(trace.get('error', ''), 500) or '-'}",
                f"- 回复预览: {_truncate_text(trace.get('response_preview', ''), 2000) or '-'}",
                "",
            ])
    else:
        lines.extend(["- 无 LLM 调用明细", ""])
    lines.extend(["## 问题", ""])
    if issues:
        for issue in issues:
            severity = severity_labels.get(str(issue.severity), str(issue.severity))
            category = category_labels.get(str(issue.category), str(issue.category))
            lines.append(
                f"- [{severity}] {category}: {issue.description}"
            )
    else:
        lines.append("- 无")
    lines.extend(["", "## 可疑样本", ""])
    if suspicious_samples:
        for sample in suspicious_samples[:20]:
            _append_review_sample_lines(lines, sample)
    else:
        lines.append("- 无")
    lines.extend(["", "## 审查样本明细", ""])
    if reviewed_samples:
        lines.append(f"- 共记录 {len(reviewed_samples)} 条样本，以下按审查顺序最多展示 80 条。")
        lines.append("")
        for sample in reviewed_samples[:80]:
            _append_review_sample_lines(lines, sample, answer_limit=2400, memory_pack_limit=900)
    else:
        lines.append("- 无")
    lines.extend(["", "## 复盘指标", ""])
    if boundary_metrics:
        token_usage_rate = boundary_metrics.get("avg_token_usage_rate", 0)
        miss_rate = boundary_metrics.get("miss_rate", 0)
        irrelevant_rate = boundary_metrics.get("irrelevant_injection_rate", 0)
        token_status = "⚠️" if token_usage_rate > 80 else "✅"
        miss_status = "⚠️" if miss_rate > 20 else "✅"
        irrelevant_status = "⚠️" if irrelevant_rate > 15 else "✅"
        lines.append(f"- 平均 token 使用率: {token_usage_rate:.1f}% {token_status}")
        lines.append(f"- 缺失率: {miss_rate:.1f}% {miss_status}")
        lines.append(f"- 无关注入率: {irrelevant_rate:.1f}% {irrelevant_status}")
        file_item_counts = boundary_metrics.get("file_item_counts", {})
        if file_item_counts:
            lines.append("- 文件条目数:")
            for file_key, count in file_item_counts.items():
                lines.append(f"  - {file_key}: {count}")
    else:
        lines.append("- 暂无边界指标")
    lines.extend(["", "## 已应用补丁", ""])
    if patches_applied:
        for patch in patches_applied:
            action = action_labels.get(str(patch.get('action', '')), str(patch.get('action', '')))
            item_content = _truncate_text(str(patch.get('item_content', '') or ''), 120)
            reason = str(patch.get('reason', '') or '')
            if item_content:
                lines.append(f"- {action} {patch.get('target_file', '')}：{item_content}（{reason}）")
            else:
                lines.append(f"- {action} {patch.get('target_file', '')}（{reason}）")
    else:
        lines.append("- 本次审核未应用补丁")
    if patch_results:
        lines.extend(["", "## 补丁执行结果", ""])
        result_sections = [
            ("applied", "已应用"),
            ("skipped", "已跳过"),
            ("errors", "执行错误"),
        ]
        has_result_message = False
        for key, label in result_sections:
            messages = patch_results.get(key, [])
            if not messages:
                continue
            has_result_message = True
            lines.append(f"### {label}")
            for message in messages:
                lines.append(f"- {message}")
            lines.append("")
        if not has_result_message:
            lines.append("- 无")
    report_path.write_text("\n".join(lines).strip() + "\n", encoding="utf-8")
    return str(report_path)


TOKEN_BUDGET_MODES = {
    "compact": {"total": 1500, "rules": 60, "explicit": 300, "work": 360, "profile": 150, "timeline": 120, "document": 360, "inbox": 150},
    "default": {"total": 4000, "rules": 120, "explicit": 720, "work": 960, "profile": 320, "timeline": 400, "document": 1200, "inbox": 280},
    "expanded": {"total": 8000, "rules": 200, "explicit": 960, "work": 1600, "profile": 560, "timeline": 800, "document": 3200, "inbox": 680},
}


def review_conversation_usage(
    audit_samples: list[dict[str, Any]],
    *,
    usage_scope: str = "chat",
    memory_root: str = ".memory",
    metadata: dict[str, Any] | None = None,
    llm: BaseChatModel | None = None,
) -> dict[str, Any]:
    if metadata is None:
        metadata = {}
    meta = ReviewMetadata(**metadata)
    memory_files = load_memory_files(memory_root)
    file_review = review_memory_files(memory_root=memory_root, metadata=metadata, llm=llm, skip_report=True)
    main_review_error = str(file_review.get("llm_error") or file_review.get("error") or "").strip()

    issues: list[Issue] = [Issue(**item) for item in file_review.get("issues", [])]
    patches: list[Patch] = [Patch(**item) for item in file_review.get("recommended_patches", [])]
    feedback_review_token_usage: dict[str, int] = {}
    reviewed_feedback_ids: list[str] = []

    priority_issues: list[Issue] = [
        issue for issue in issues if str(issue.issue_id or "").startswith("priority-dup-")
    ]

    suspicious_samples: list[dict[str, Any]] = []
    reviewed_sample_details: list[dict[str, Any]] = []
    review_traces: list[dict[str, Any]] = []
    if isinstance(file_review.get("llm_review_trace"), dict):
        review_traces.append(dict(file_review["llm_review_trace"]))
    counters = {
        "used_effectively": 0,
        "used_but_wasteful": 0,
        "needed_but_missed": 0,
        "irrelevant_injection": 0,
        "priority_violation": len(priority_issues),
        "budget_overrun": 0,
        "feedback_useless": 0,
        "feedback_useful": 0,
        "feedback_useless_reviewed": 0,
        "feedback_useless_review_failed": 0,
    }
    budget_limit = max(200, int(meta.token_budget or TOKEN_BUDGET_MODES["default"]["total"]))

    for sample in audit_samples:
        budget_used = max(0, int(sample.get("token_budget_used_estimate", 0) or 0))
        needs_more_memory = bool(sample.get("needs_more_memory", False))
        status = str(sample.get("status", "") or "").strip().lower()
        final_answer = str(sample.get("final_answer", "") or "").strip()
        memory_pack = str(sample.get("memory_pack", "") or "").strip()
        selected_files = [str(item) for item in sample.get("selected_files", [])]
        feedback_result = str(sample.get("feedback_result", "") or "").strip().lower()
        feedback_id = str(sample.get("feedback_id") or sample.get("trace_id") or "").strip()
        feedback_reason = str(sample.get("feedback_reason", "") or "").strip()
        is_useless_feedback = feedback_result == "useless"
        is_useful_feedback = feedback_result == "useful"
        if is_useless_feedback:
            counters["feedback_useless"] += 1
        elif is_useful_feedback:
            counters["feedback_useful"] += 1

        if status == "failed" and needs_more_memory:
            counters["needed_but_missed"] += 1
        elif budget_used > budget_limit:
            counters["used_but_wasteful"] += 1
        elif memory_pack and not final_answer:
            counters["irrelevant_injection"] += 1
        else:
            counters["used_effectively"] += 1

        sample_issues: list[Issue] = []

        if budget_used > budget_limit:
            counters["budget_overrun"] += 1
            sample_issues.append(Issue(
                issue_id=f"usage-budget",
                severity="medium",
                category="token_over_budget",
                description=f"记忆包消耗 {budget_used} tokens，超过预算 {budget_limit}",
                affected_files=selected_files,
            ))

        if needs_more_memory:
            sample_issues.append(Issue(
                issue_id=f"usage-missing",
                severity="medium",
                category="missing_memory",
                description="读取器判断当前回答需要更多记忆支持",
                affected_files=selected_files,
            ))

        if is_useless_feedback:
            reason_suffix = f"；用户填写原因：{feedback_reason}" if feedback_reason else ""
            sample_issues.append(Issue(
                issue_id=f"feedback-useless-{feedback_id[:32] or 'sample'}",
                severity="high",
                category="missing_memory",
                description=f"用户将该回复标记为无用，需要优先审查是否存在记忆缺失、错误记忆、召回不当或回答质量问题{reason_suffix}",
                affected_files=selected_files,
            ))
            if llm is not None:
                try:
                    feedback_review = run_review_chain(
                        review_type="memory_pack",
                        memory_files=memory_files,
                        current_message=str(sample.get("user_query") or ""),
                        agent_answer=final_answer,
                        memory_pack=memory_pack,
                        user_feedback=_feedback_review_text(sample, feedback_reason),
                        llm=llm,
                    )
                    if not isinstance(feedback_review, dict):
                        feedback_review = {}
                    if isinstance(feedback_review.get("llm_review_trace"), dict):
                        trace = dict(feedback_review["llm_review_trace"])
                        trace["feedback_id"] = feedback_id
                        trace["trace_id"] = str(sample.get("trace_id", ""))
                        review_traces.append(trace)
                    _merge_token_usage(feedback_review_token_usage, dict(feedback_review.get("token_usage", {}) or {}))
                    feedback_review_error = str(
                        feedback_review.get("llm_error") or feedback_review.get("error") or ""
                    ).strip()
                    if feedback_review_error:
                        counters["feedback_useless_review_failed"] += 1
                        logger.warning(
                            "Useless feedback root-cause review failed for %s: %s",
                            feedback_id or sample.get("trace_id", "sample"),
                            feedback_review_error,
                        )
                    else:
                        counters["feedback_useless_reviewed"] += 1
                        if feedback_id:
                            reviewed_feedback_ids.append(feedback_id)
                        for raw_issue in feedback_review.get("issues", []):
                            issue = _raw_issue_to_issue(raw_issue, default_category="missing_memory", default_severity="high")
                            if not issue.issue_id:
                                issue.issue_id = f"feedback-root-{feedback_id[:32] or 'sample'}"
                            if not issue.affected_files:
                                issue.affected_files = selected_files
                            sample_issues.append(issue)
                        patch_counter = len(patches)
                        for raw_patch in feedback_review.get("recommended_patches", []):
                            patch_counter += 1
                            if isinstance(raw_patch, dict):
                                patches.append(_raw_patch_to_patch(raw_patch, prefix="fb", counter=patch_counter))
                except Exception as exc:
                    counters["feedback_useless_review_failed"] += 1
                    logger.warning(
                        "Useless feedback root-cause review failed for %s: %s",
                        feedback_id or sample.get("trace_id", "sample"),
                        exc,
                    )

        sample_detail = _review_sample_detail(
            sample,
            status=status,
            selected_files=selected_files,
            budget_used=budget_used,
            needs_more_memory=needs_more_memory,
            final_answer=final_answer,
            memory_pack=memory_pack,
            feedback_id=feedback_id,
            feedback_result=feedback_result,
            feedback_reason=feedback_reason,
            sample_issues=sample_issues,
        )
        reviewed_sample_details.append(sample_detail)

        if sample_issues:
            suspicious_samples.append(sample_detail)
            issues.extend(sample_issues)

    patches = _dedupe_patches([], patches)
    quality_score = max(0, min(int(file_review.get("quality_score", 100)), _compute_quality_score(issues, max(1, len(audit_samples)))))
    review_summary = (
        f"已审核 {len(audit_samples)} 条审计样本；"
        f"有效使用 {counters['used_effectively']} 条，"
        f"使用但浪费 {counters['used_but_wasteful']} 条，"
        f"需要但未命中 {counters['needed_but_missed']} 条，"
        f"无关注入 {counters['irrelevant_injection']} 条，"
        f"用户无用反馈 {counters['feedback_useless']} 条，"
        f"用户有用反馈 {counters['feedback_useful']} 条，"
        f"无用反馈根因审查 {counters['feedback_useless_reviewed']} 条，"
        f"根因审查失败 {counters['feedback_useless_review_failed']} 条"
    )
    if main_review_error:
        review_summary = f"{review_summary}；主审核 LLM 失败: {main_review_error[:300]}"

    total_samples = len(audit_samples) or 1
    avg_budget_used = sum(
        max(0, int(s.get("token_budget_used_estimate", 0) or 0)) for s in audit_samples
    ) / total_samples
    avg_token_usage_rate = (avg_budget_used / budget_limit) * 100 if budget_limit else 0.0
    miss_count = sum(1 for s in audit_samples if bool(s.get("needs_more_memory", False)))
    miss_rate = (miss_count / total_samples) * 100
    irrelevant_count = counters.get("irrelevant_injection", 0)
    irrelevant_rate = (irrelevant_count / total_samples) * 100

    boundary_metrics = {
        "avg_token_usage_rate": avg_token_usage_rate,
        "miss_rate": miss_rate,
        "irrelevant_injection_rate": irrelevant_rate,
        "file_item_counts": {},
    }

    patch_results: dict[str, list[str]] | None = None
    if meta.mode == "patch" and patches:
        patch_results = apply_patch_plan(patches, memory_root, dry_run=False)
    elif meta.mode == "dry_run":
        patch_results = apply_patch_plan(patches, memory_root, dry_run=True)

    patches_applied_for_report = _patches_applied_for_report(patches, patch_results)
    token_usage = dict(file_review.get("token_usage", {}) or {})
    _merge_token_usage(token_usage, feedback_review_token_usage)

    timestamp = datetime.now().strftime("%Y-%m-%d_%H-%M")
    if usage_scope == "document":
        report_name = f"文档记忆使用审核_{timestamp}.md"
        title = "文档记忆使用审核"
    else:
        report_name = f"会话记忆使用审核_{timestamp}.md"
        title = "会话记忆使用审核"
    report_path = _write_review_report(
        memory_root,
        report_name=report_name,
        title=title,
        summary=review_summary,
        counters=counters,
        suspicious_samples=suspicious_samples,
        issues=issues,
        reviewed_samples=reviewed_sample_details,
        patches_applied=patches_applied_for_report,
        patch_results=patch_results,
        boundary_metrics=boundary_metrics,
        token_usage=token_usage,
        review_prompt=str(metadata.get("review_prompt", "") or ""),
        review_traces=review_traces,
    )

    output = ReviewOutput(
        review_summary=review_summary,
        quality_score=quality_score,
        issues=issues,
        recommended_patches=patches,
        compress_suggestions=file_review.get("compress_suggestions", []),
        promote_suggestions=file_review.get("promote_suggestions", []),
        items_to_merge=file_review.get("items_to_merge", []),
        items_to_delete=file_review.get("items_to_delete", []),
        items_to_deprecate=file_review.get("items_to_deprecate", []),
        items_to_move_to_inbox=file_review.get("items_to_move_to_inbox", []),
        items_to_compress=file_review.get("items_to_compress", []),
        missing_memory_warnings=file_review.get("missing_memory_warnings", []),
        conflicts=[Conflict(**item) for item in file_review.get("conflicts", [])],
        changelog_items=file_review.get("changelog_items", []),
        safe_to_apply=_is_safe_to_apply(patches),
        token_usage=token_usage,
        boundary_metrics=boundary_metrics,
    ).model_dump()
    output["usage_counters"] = counters
    output["reviewed_samples"] = len(audit_samples)
    output["suspicious_samples"] = suspicious_samples[:20]
    output["reviewed_sample_details"] = reviewed_sample_details[:80]
    output["review_traces"] = review_traces[:10]
    output["report_path"] = report_path
    output["reviewed_feedback_ids"] = list(dict.fromkeys(reviewed_feedback_ids))
    output["ok"] = not bool(main_review_error)
    if main_review_error:
        output["error"] = f"主审核 LLM 失败: {main_review_error}"
        output["llm_error"] = main_review_error
    if patch_results is not None:
        output["patch_results"] = patch_results

    return output
