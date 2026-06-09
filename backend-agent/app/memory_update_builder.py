from __future__ import annotations

"""记忆更新操作构建模块。

根据聊天消息和用户反馈构建记忆更新预览，包括 QA 对的组织、
AI 自动回复的筛选与优先级排序、反馈标注和字符限制处理，
为记忆提取任务提供结构化的输入数据。
"""

import copy
from typing import Any
from pathlib import Path

from app.db.feedback_store import get_feedback_by_message_ids
from app.db.message_store import (
    list_unconverted_messages_with_chat_info,
    organize_messages_into_qa_pairs,
)
from app.db.settings_store import get_platform_settings
from app.utils import utc_last_hour, utc_now

DEFAULT_MEMORY_UPDATE_MAX_PAIRS = 100
DEFAULT_MEMORY_UPDATE_MAX_CHARS = 15000
AI_AUTO_REPLY_SOURCES = {"ai"}
AI_AUTO_REPLY_MSG_TYPES = {"agent"}


def get_memory_update_limits() -> dict[str, int]:
    settings = get_platform_settings()
    max_pairs = int(settings.get("memory_update_max_pairs", DEFAULT_MEMORY_UPDATE_MAX_PAIRS) or DEFAULT_MEMORY_UPDATE_MAX_PAIRS)
    max_chars = int(settings.get("memory_update_max_chars", DEFAULT_MEMORY_UPDATE_MAX_CHARS) or DEFAULT_MEMORY_UPDATE_MAX_CHARS)
    return {
        "max_pairs": max(1, max_pairs),
        "max_chars": max(1000, max_chars),
    }


def build_memory_update_preview(
    database_path: Path,
    *,
    cutoff_time: str | None = None,
) -> dict[str, Any]:
    current_time = utc_now()
    effective_cutoff = cutoff_time or utc_last_hour()
    limits = get_memory_update_limits()

    messages_with_chat_info = list_unconverted_messages_with_chat_info(
        database_path,
        end_time=effective_cutoff,
    )
    qa_data = organize_messages_into_qa_pairs(messages_with_chat_info)
    answer_message_ids = _collect_answer_message_ids(qa_data)
    feedback_by_message_id = get_feedback_by_message_ids(database_path, answer_message_ids)

    selected_chats: dict[str, dict[str, Any]] = {}
    selected_message_ids: dict[str, list[str]] = {}
    skipped_ai_message_ids: dict[str, list[str]] = {}
    included_pair_count = 0
    included_char_count = 0
    included_useful_ai_pair_count = 0
    included_useful_ai_message_count = 0
    included_mixed_ai_pair_count = 0
    included_mixed_ai_message_count = 0
    omitted_pair_count = 0
    omitted_message_count = 0
    skipped_ai_pair_count = 0
    skipped_ai_message_count = 0
    skipped_useless_ai_pair_count = 0
    skipped_useless_ai_message_count = 0
    total_pair_count = 0
    total_message_count = sum(len(msgs) for msgs in messages_with_chat_info.values())
    candidate_records: list[dict[str, Any]] = []
    sequence = 0

    for chat_id, chat_info in qa_data.items():
        pairs = chat_info.get("pairs") or []
        total_pair_count += len(pairs)
        skipped_ai_ids: list[str] = []

        for pair in pairs:
            sequence += 1
            feedbacks = _answer_feedbacks(pair, feedback_by_message_id)
            annotated_pair = _annotate_pair_feedbacks(pair, feedbacks)
            message_ids = _pair_message_ids(annotated_pair)
            is_ai_pair = is_ai_auto_reply_pair(annotated_pair)
            feedback_status = _pair_feedback_status(annotated_pair)

            if is_ai_pair and feedback_status not in {"useful_only", "mixed"}:
                skipped_ai_pair_count += 1
                skipped_ai_message_count += len(message_ids)
                if feedback_status == "useless_only":
                    skipped_useless_ai_pair_count += 1
                    skipped_useless_ai_message_count += len(message_ids)
                skipped_ai_ids.extend(message_ids)
                continue

            pair_chars = _estimate_pair_chars(annotated_pair)
            candidate_records.append({
                "id": len(candidate_records),
                "chat_id": chat_id,
                "chat_info": chat_info,
                "pair": annotated_pair,
                "message_ids": message_ids,
                "is_ai_pair": is_ai_pair,
                "feedback_status": feedback_status,
                "pair_chars": pair_chars,
                "priority": _memory_extraction_priority(is_ai_pair, feedback_status),
                "sequence": sequence,
            })

        if skipped_ai_ids:
            skipped_ai_message_ids[chat_id] = _dedupe_preserve_order(skipped_ai_ids)

    selected_record_ids: set[int] = set()
    for record in sorted(candidate_records, key=lambda item: (item["priority"], item["sequence"])):
        message_ids = record["message_ids"]
        pair_chars = int(record["pair_chars"])
        would_exceed_pairs = included_pair_count >= limits["max_pairs"]
        would_exceed_chars = included_pair_count > 0 and (included_char_count + pair_chars > limits["max_chars"])
        if would_exceed_pairs or would_exceed_chars:
            omitted_pair_count += 1
            omitted_message_count += len(message_ids)
            continue

        selected_record_ids.add(int(record["id"]))
        included_pair_count += 1
        included_char_count += pair_chars
        if record["is_ai_pair"]:
            if record["feedback_status"] == "useful_only":
                included_useful_ai_pair_count += 1
                included_useful_ai_message_count += len(message_ids)
            elif record["feedback_status"] == "mixed":
                included_mixed_ai_pair_count += 1
                included_mixed_ai_message_count += len(message_ids)

    for record in sorted(candidate_records, key=lambda item: item["sequence"]):
        if int(record["id"]) not in selected_record_ids:
            continue
        chat_id = str(record["chat_id"])
        chat_info = record["chat_info"]
        if chat_id not in selected_chats:
            selected_chats[chat_id] = {
                "chat_name": chat_info.get("chat_name", ""),
                "chat_display_name": chat_info.get("chat_display_name", ""),
                "chat_type": chat_info.get("chat_type", ""),
                "pairs": [],
            }
        selected_chats[chat_id]["pairs"].append(record["pair"])
        selected_message_ids.setdefault(chat_id, []).extend(record["message_ids"])

    selected_message_ids = {
        chat_id: _dedupe_preserve_order(ids)
        for chat_id, ids in selected_message_ids.items()
        if ids
    }

    payload = {
        "cutoff_time": effective_cutoff,
        "chats": selected_chats,
        "extraction_message_ids": selected_message_ids,
        "skipped_ai_message_ids": skipped_ai_message_ids,
        "skipped_ai_pair_count": skipped_ai_pair_count,
        "skipped_ai_message_count": skipped_ai_message_count,
        "included_useful_ai_pair_count": included_useful_ai_pair_count,
        "included_useful_ai_message_count": included_useful_ai_message_count,
        "included_mixed_ai_pair_count": included_mixed_ai_pair_count,
        "included_mixed_ai_message_count": included_mixed_ai_message_count,
        "skipped_useless_ai_pair_count": skipped_useless_ai_pair_count,
        "skipped_useless_ai_message_count": skipped_useless_ai_message_count,
    }
    return {
        "cutoff_time": effective_cutoff,
        "current_time": current_time,
        "chat_count": len(selected_chats),
        "total_message_count": total_message_count,
        "total_pair_count": total_pair_count,
        "selected_message_count": sum(len(ids) for ids in selected_message_ids.values()),
        "selected_pair_count": included_pair_count,
        "selected_char_count": included_char_count,
        "mark_message_count": (
            sum(len(ids) for ids in selected_message_ids.values())
            + sum(len(ids) for ids in skipped_ai_message_ids.values())
        ),
        "skipped_ai_pair_count": skipped_ai_pair_count,
        "skipped_ai_message_count": skipped_ai_message_count,
        "included_useful_ai_pair_count": included_useful_ai_pair_count,
        "included_useful_ai_message_count": included_useful_ai_message_count,
        "included_mixed_ai_pair_count": included_mixed_ai_pair_count,
        "included_mixed_ai_message_count": included_mixed_ai_message_count,
        "skipped_useless_ai_pair_count": skipped_useless_ai_pair_count,
        "skipped_useless_ai_message_count": skipped_useless_ai_message_count,
        "omitted_pair_count": omitted_pair_count,
        "omitted_message_count": omitted_message_count,
        "is_truncated": bool(omitted_pair_count or omitted_message_count),
        "limits": limits,
        "chats": selected_chats,
        "extraction_message_ids": selected_message_ids,
        "skipped_ai_message_ids": skipped_ai_message_ids,
        "auto_generated": True,
        "payload": payload,
    }


def is_ai_auto_reply_pair(pair: dict[str, Any]) -> bool:
    reply_source = str(
        pair.get("answer_reply_source")
        or pair.get("direction")
        or ""
    ).strip().lower()
    msg_type = str(pair.get("answer_msg_type") or "").strip().lower()
    return reply_source in AI_AUTO_REPLY_SOURCES or msg_type in AI_AUTO_REPLY_MSG_TYPES


def is_user_confirmed_ai_pair(pair: dict[str, Any]) -> bool:
    return is_ai_auto_reply_pair(pair) and _pair_feedback_status(pair) in {"useful_only", "mixed"}


def _memory_extraction_priority(is_ai_pair: bool, feedback_status: str) -> int:
    if is_ai_pair and feedback_status == "useful_only":
        return 0
    if is_ai_pair and feedback_status == "mixed":
        return 1
    return 2


def _collect_answer_message_ids(qa_data: dict[str, dict[str, Any]]) -> list[str]:
    ids: list[str] = []
    for chat_info in qa_data.values():
        for pair in chat_info.get("pairs") or []:
            value = pair.get("answer_message_ids")
            if not isinstance(value, list):
                continue
            for item in value:
                text = str(item or "").strip()
                if text:
                    ids.append(text)
    return _dedupe_preserve_order(ids)


def _answer_feedbacks(
    pair: dict[str, Any],
    feedback_by_message_id: dict[str, list[dict[str, Any]]],
) -> list[dict[str, Any]]:
    all_feedbacks: list[dict[str, Any]] = []
    value = pair.get("answer_message_ids")
    if isinstance(value, list):
        for item in value:
            message_id = str(item or "").strip()
            feedbacks = feedback_by_message_id.get(message_id)
            if feedbacks:
                all_feedbacks.extend(feedbacks)
    all_feedbacks.sort(key=lambda item: str(item.get("created_at") or ""), reverse=True)
    seen: set[str] = set()
    deduped: list[dict[str, Any]] = []
    for fb in all_feedbacks:
        fid = str(fb.get("id") or "").strip()
        if fid and fid in seen:
            continue
        if fid:
            seen.add(fid)
        deduped.append(fb)
    return deduped


def _annotate_pair_feedbacks(pair: dict[str, Any], feedbacks: list[dict[str, Any]]) -> dict[str, Any]:
    annotated = copy.deepcopy(pair)
    if not feedbacks:
        return annotated
    primary = feedbacks[0]
    results = set(str(fb.get("result") or "").strip().lower() for fb in feedbacks)
    has_useful = "useful" in results
    has_useless = "useless" in results
    if has_useful and has_useless:
        status = "mixed"
    elif has_useless:
        status = "useless_only"
    elif has_useful:
        status = "useful_only"
    else:
        status = ""
    useless_reasons = [str(fb.get("reason") or "").strip() for fb in feedbacks if str(fb.get("result") or "").strip().lower() == "useless" and str(fb.get("reason") or "").strip()]
    annotated["answer_feedback_id"] = str(primary.get("id") or "")
    annotated["answer_feedback_result"] = str(primary.get("result") or "").strip().lower()
    annotated["answer_feedback_at"] = str(primary.get("created_at") or "")
    annotated["answer_feedback_user_id"] = str(primary.get("user_id") or "")
    annotated["answer_feedback_msg_id"] = str(primary.get("msg_id") or "")
    annotated["answer_feedback_reason"] = str(primary.get("reason") or "").strip()
    annotated["answer_feedback_status"] = status
    annotated["answer_feedback_all_reasons"] = "；".join(useless_reasons)
    annotated["answer_feedback_count"] = len(feedbacks)
    return annotated


def _pair_feedback_status(pair: dict[str, Any]) -> str:
    return str(pair.get("answer_feedback_status") or "").strip().lower()


def _pair_feedback_result(pair: dict[str, Any]) -> str:
    return str(pair.get("answer_feedback_result") or "").strip().lower()


def _estimate_pair_chars(pair: dict[str, Any]) -> int:
    question = str(pair.get("question") or "").strip()
    answer = str(pair.get("answer") or "").strip()
    question_sender = str(pair.get("question_sender") or "").strip()
    answer_sender = str(pair.get("answer_sender") or "").strip()
    return len(question) + len(answer) + len(question_sender) + len(answer_sender) + 32


def _pair_message_ids(pair: dict[str, Any]) -> list[str]:
    ids: list[str] = []
    for key in ("question_message_ids", "answer_message_ids"):
        value = pair.get(key)
        if not isinstance(value, list):
            continue
        for item in value:
            text = str(item or "").strip()
            if text:
                ids.append(text)
    return _dedupe_preserve_order(ids)


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result
