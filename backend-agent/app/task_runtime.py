from __future__ import annotations

"""任务运行时执行模块。

实现各类任务的运行时执行逻辑，包括数据库清理、文档记忆提取、
显式记忆生成、记忆更新、聊天/文档记忆自审查和 Bot 任务等，
提供任务调度、Token 用量记录和完成通知等功能。
"""

import asyncio
import json
import logging
import time
from datetime import datetime
from pathlib import Path
from typing import Any

from app.bot_process_manager import BotProcessManager
from app.database import optimize_database
from app.db.bot_store import get_bot_config, make_conversation_key
from app.db.core import connect_database
from app.db.bot_store import list_bot_configs
from app.db.document_store import get_document_by_id, update_document_parse_status, update_document_convert_status
from app.db.feedback_store import list_recent_feedback_review_samples
from app.db.log_store import insert_project_log
from app.db.memory_usage_audit_store import list_recent_memory_usage_audits
from app.db.message_store import list_unconverted_messages, mark_messages_converted, list_unconverted_messages_with_chat_info, organize_messages_into_qa_pairs
from app.db.settings_store import load_settings_from_database
from app.db.task_store import ensure_default_periodic_tasks, ensure_agent_dependent_tasks
from app.db.token_usage_store import record_token_usage
from app.document_text_extractor import extract_text_from_file
from app.manual_reply_queue import enqueue_manual_reply, get_manual_reply
from app.memory_update_builder import build_memory_update_preview, is_ai_auto_reply_pair, is_user_confirmed_ai_pair


MEMORY_UPDATE_REVIEW_REQUIRED_PREFIX = "[memory_update_manual_review]"
VALID_REVIEW_MODES = {"review", "dry_run", "patch"}


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    result: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            result.append(text)
    return result


def _parse_bot_task_prompt_data(prompt_text: Any) -> dict[str, Any]:
    raw_text = str(prompt_text or "").strip()
    payload = {
        "user_prompt": raw_text,
        "skill_names": [],
        "mcp_server_ids": [],
    }
    if not raw_text:
        return payload
    try:
        data = json.loads(raw_text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return payload
    if not isinstance(data, dict):
        return payload

    payload = {
        "user_prompt": str(data.get("user_prompt") or ""),
        "skill_names": _normalize_string_list(data.get("skill_names")),
        "mcp_server_ids": _normalize_string_list(data.get("mcp_server_ids")),
    }

    nested_text = payload["user_prompt"].strip()
    if not nested_text:
        return payload
    try:
        nested = json.loads(nested_text)
    except (json.JSONDecodeError, TypeError, ValueError):
        return payload
    if not isinstance(nested, dict):
        return payload
    if not any(key in nested for key in ("user_prompt", "skill_names", "mcp_server_ids")):
        return payload

    nested_user_prompt = str(nested.get("user_prompt") or "").strip()
    if nested_user_prompt:
        payload["user_prompt"] = nested_user_prompt
    if not payload["skill_names"]:
        payload["skill_names"] = _normalize_string_list(nested.get("skill_names"))
    if not payload["mcp_server_ids"]:
        payload["mcp_server_ids"] = _normalize_string_list(nested.get("mcp_server_ids"))
    return payload


def _parse_review_prompt_and_mode(task: dict[str, Any]) -> tuple[str, str, str]:
    raw = str(task.get("prompt_text") or "").strip()
    mode = "review"
    prompt = ""
    suggestion = ""
    try:
        data = json.loads(raw)
        if isinstance(data, dict):
            m = str(data.get("review_mode", "") or "").strip()
            if m in VALID_REVIEW_MODES:
                mode = m
            prompt = str(data.get("review_prompt", "") or "").strip()
            suggestion = str(data.get("review_suggestion", "") or "").strip()
    except (json.JSONDecodeError, ValueError):
        pass
    return prompt, mode, suggestion


def _extract_token_usage(payload: dict[str, Any] | None) -> dict[str, int]:
    if not isinstance(payload, dict):
        return {}
    raw = payload.get("token_usage")
    if not isinstance(raw, dict):
        return {}
    input_tokens = int(raw.get("input_tokens", 0) or 0)
    output_tokens = int(raw.get("output_tokens", 0) or 0)
    total_tokens = int(raw.get("total_tokens", 0) or (input_tokens + output_tokens))
    return {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": total_tokens,
    }


def _json_preview(value: Any, max_chars: int = 8000) -> str:
    try:
        text = json.dumps(value, ensure_ascii=False, default=str)
    except (TypeError, ValueError):
        text = str(value or "")
    if len(text) <= max_chars:
        return text
    return text[: max(0, max_chars - 20)].rstrip() + "...[已截断]"


def _resolve_provider_details(settings: Any) -> tuple[str, str, str]:
    try:
        provider_key = str(getattr(settings.agent, "provider", "") or "")
        provider = settings.agent.providers.get(provider_key)
        return (
            provider_key,
            str(getattr(provider, "type", "") or ""),
            str(getattr(provider, "model", "") or ""),
        )
    except Exception:
        return "", "", ""


def _log_agent_prompt_payload(
    database_path: Path,
    *,
    trace_id: str,
    call_type: str,
    detail_lines: list[str],
) -> None:
    insert_project_log(
        database_path,
        trace_id=trace_id,
        level="INFO",
        category="ai",
        source="agent.prompt",
        message="Agent prompt payload",
        detail="\n".join([f"call_type={call_type}", *detail_lines]),
    )


def _log_agent_answer_payload(
    database_path: Path,
    *,
    trace_id: str,
    call_type: str,
    detail_lines: list[str],
) -> None:
    insert_project_log(
        database_path,
        trace_id=trace_id,
        level="INFO",
        category="ai",
        source="agent.answer",
        message="Agent answer payload",
        detail="\n".join([f"call_type={call_type}", *detail_lines]),
    )


def _record_task_token_usage(
    database_path: Path,
    *,
    trace_id: str,
    call_type: str,
    token_usage: dict[str, int],
    provider_key: str = "",
    provider_type: str = "",
    model: str = "",
) -> None:
    input_tokens = int(token_usage.get("input_tokens", 0) or 0)
    output_tokens = int(token_usage.get("output_tokens", 0) or 0)
    total_tokens = int(token_usage.get("total_tokens", 0) or (input_tokens + output_tokens))
    if total_tokens > 0 or input_tokens > 0 or output_tokens > 0:
        record_token_usage(
            database_path,
            provider_key=provider_key,
            provider_type=provider_type,
            model=model,
            call_type=call_type,
            trace_id=trace_id,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
            total_tokens=total_tokens,
        )


def _log_task_token_usage_payload(
    database_path: Path,
    *,
    trace_id: str,
    call_type: str,
    token_usage: dict[str, int],
    provider_key: str = "",
    provider_type: str = "",
    model: str = "",
) -> None:
    insert_project_log(
        database_path,
        trace_id=trace_id,
        level="INFO",
        category="ai",
        source="token_usage",
        message="Task token usage",
        detail="\n".join([
            f"call_type={call_type}",
            f"provider_key={provider_key}",
            f"provider_type={provider_type}",
            f"model={model}",
            f"input_tokens={int(token_usage.get('input_tokens', 0) or 0)}",
            f"output_tokens={int(token_usage.get('output_tokens', 0) or 0)}",
            f"total_tokens={int(token_usage.get('total_tokens', 0) or 0)}",
        ]),
    )


def _normalize_bot_task_result_text(result_text: str) -> str:
    text = str(result_text or "").strip()
    if not text:
        return ""
    if text.lower() == "none":
        return ""
    filtered_lines: list[str] = []
    for line in text.splitlines():
        normalized = line.strip().strip("`").strip()
        if normalized.lower() in {"notify-me", "notify_me", "none"}:
            continue
        filtered_lines.append(line.rstrip())
    return "\n".join(filtered_lines).strip()


def _is_notify_skip_payload(result_text: str) -> bool:
    text = str(result_text or "").strip()
    if not text.startswith("{"):
        return False
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return False
    return bool(payload.get("ok")) and bool(payload.get("skipped"))


def _extract_notify_delivery_result_text(database_path: Path, *, trace_id: str, bot_key: str) -> str:
    if not trace_id or not bot_key:
        return ""
    with connect_database(database_path) as conn:
        row = conn.execute(
            """
            SELECT content
            FROM manual_reply_commands
            WHERE bot_key = ?
              AND metadata_json LIKE ?
              AND metadata_json LIKE ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (
                bot_key,
                '%"trace_id": "' + trace_id + '"%',
                '%"source": "notify_me_skill"%',
            ),
        ).fetchone()
        if row is None:
            row = conn.execute(
                """
                SELECT content
                FROM manual_reply_commands
                WHERE bot_key = ?
                  AND metadata_json LIKE ?
                  AND metadata_json LIKE ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (
                    bot_key,
                    '%"trace_id": "' + trace_id + '"%',
                    '%"source": "bot_task_runtime"%',
                ),
            ).fetchone()
    if row is None:
        return ""
    content = str(row["content"] or "").strip()
    if not content:
        return ""
    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if len(lines) >= 2:
        return "\n".join(lines[1:]).strip().strip('"')
    return content.strip('"')


def _has_notify_me_delivery(database_path: Path, *, trace_id: str, bot_key: str) -> bool:
    if not trace_id or not bot_key:
        return False
    with connect_database(database_path) as conn:
        row = conn.execute(
            """
            SELECT 1
            FROM manual_reply_commands
            WHERE bot_key = ?
              AND metadata_json LIKE ?
              AND metadata_json LIKE ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (
                bot_key,
                '%"source": "notify_me_skill"%',
                f'%"trace_id": "{trace_id}"%',
            ),
        ).fetchone()
    return row is not None


def _send_bot_task_result_notification(
    database_path: Path,
    *,
    bot_key: str,
    task_key: str,
    task_name: str,
    result_text: str,
    trace_id: str,
) -> tuple[bool, str]:
    bot = get_bot_config(database_path, bot_key)
    if not bot:
        return False, "Bot 配置不存在"

    bound_chat_id = str(bot.get("bound_chat_id") or "").strip()
    if not bound_chat_id:
        return False, "Bot 未绑定管理员会话"

    conversation_chat_id = make_conversation_key(bot_key, bound_chat_id, kind="me")
    with connect_database(database_path) as conn:
        row = conn.execute(
            """
            SELECT chat_id, chat_name, display_name
            FROM conversations
            WHERE chat_id = ?
            LIMIT 1
            """,
            (conversation_chat_id,),
        ).fetchone()
    if row is None:
        return False, "管理员会话不存在"

    chat_name = str(row["display_name"] or row["chat_name"] or bound_chat_id).strip() or bound_chat_id
    content = "\n".join(
        [
            f"任务完成：{task_name}",
            "",
            result_text,
        ]
    ).strip()
    command = enqueue_manual_reply(
        chat_id=bound_chat_id,
        chat_name=chat_name,
        content=content,
        database_path=database_path,
        bot_key=bot_key,
        conversation_chat_id=conversation_chat_id,
        external_chat_id=bound_chat_id,
        metadata={
            "source": "bot_task_runtime",
            "task_key": task_key,
            "trace_id": trace_id,
        },
        skip_record=True,
    )
    deadline = time.time() + 30.0
    while time.time() < deadline:
        status = get_manual_reply(command.id, database_path=database_path)
        state = str(status.get("status") or "")
        if state == "sent":
            return True, command.id
        if state == "failed":
            return False, str(status.get("error") or "通知发送失败")
        time.sleep(0.2)
    return False, "通知发送超时"


def _send_task_completion_notification(
    database_path: Path,
    *,
    bot_key: str,
    task_key: str,
    task_name: str,
    call_type: str,
    ok: bool,
    summary: str,
    trace_id: str,
    detail_lines: list[str] | None = None,
) -> None:
    bot = get_bot_config(database_path, bot_key)
    if not bot:
        return

    bound_chat_id = str(bot.get("bound_chat_id") or "").strip()
    if not bound_chat_id:
        return

    conversation_chat_id = make_conversation_key(bot_key, bound_chat_id, kind="me")
    with connect_database(database_path) as conn:
        row = conn.execute(
            """
            SELECT chat_id, chat_name, display_name
            FROM conversations
            WHERE chat_id = ?
            LIMIT 1
            """,
            (conversation_chat_id,),
        ).fetchone()
    if row is None:
        return

    chat_name = str(row["display_name"] or row["chat_name"] or bound_chat_id).strip() or bound_chat_id

    if ok:
        lines = [f"✅ {task_name}完成"]
        if summary:
            lines.append(f"📊 {summary}")
        if detail_lines:
            for dl in detail_lines[:8]:
                lines.append(f"  {dl}")
        content = "\n".join(lines)
    else:
        content = f"❌ {task_name}：{summary}"
    command = enqueue_manual_reply(
        chat_id=bound_chat_id,
        chat_name=chat_name,
        content=content,
        database_path=database_path,
        bot_key=bot_key,
        conversation_chat_id=conversation_chat_id,
        external_chat_id=bound_chat_id,
        metadata={
            "source": f"{call_type}_runtime",
            "task_key": task_key,
            "trace_id": trace_id,
        },
        skip_record=True,
    )
    deadline = time.time() + 30.0
    while time.time() < deadline:
        status = get_manual_reply(command.id, database_path=database_path)
        state = str(status.get("status") or "")
        if state == "sent":
            insert_project_log(
                database_path,
                trace_id=trace_id,
                level="INFO",
                category="task",
                source=call_type,
                message="任务完成通知已发送",
                detail=f"task_key={task_key}\nbot_key={bot_key}\ncommand_id={command.id}",
            )
            return
        if state == "failed":
            insert_project_log(
                database_path,
                trace_id=trace_id,
                level="WARNING",
                category="task",
                source=call_type,
                message="任务完成通知发送失败",
                detail=f"task_key={task_key}\nbot_key={bot_key}\nerror={status.get('error', '')}",
            )
            return
        time.sleep(0.2)
    insert_project_log(
        database_path,
        trace_id=trace_id,
        level="WARNING",
        category="task",
        source=call_type,
        message="任务完成通知发送超时",
        detail=f"task_key={task_key}\nbot_key={bot_key}",
    )


def ensure_task_runtime(database_path: Path) -> None:
    ensure_default_periodic_tasks(database_path)
    ensure_agent_dependent_tasks(database_path)


def run_database_cleanup_task(
    database_path: Path,
    manager: BotProcessManager,
    *,
    trace_id: str | None = None,
    source: str,
    category: str,
) -> dict[str, Any]:
    bots = list_bot_configs(database_path)
    statuses_before = manager.all_statuses(bots)
    running_bot_keys = [
        str(bot_key)
        for bot_key, item in statuses_before.items()
        if bool(item.get("running"))
    ]
    manager.stop_all()
    try:
        result = optimize_database(
            database_path,
            retention_days=30,
            log_retention_days=15,
            ai_work_retention_days=30,
            token_usage_retention_days=30,
            one_time_task_retention_days=30,
        )
        result["stopped_bots"] = len(running_bot_keys)
        result["stopped_bot_keys"] = running_bot_keys
        result["restarted_bots"] = 0
        result["restarted_bot_keys"] = []
        result["restart_errors"] = []
        result["restart_skipped"] = True
        insert_project_log(
            database_path,
            trace_id=trace_id,
            level="INFO",
            category=category,
            source=source,
            message="Database optimized",
            detail=(
                f"stopped_bots={result['stopped_bots']}, "
                f"removed_messages={result['removed_messages']}, "
                f"removed_conversations={result['removed_conversations']}, "
                f"removed_manual_reply_commands={result['removed_manual_reply_commands']}, "
                f"removed_logs={result['removed_logs']}, "
                f"removed_ai_work_items={result['removed_ai_work_items']}, "
                f"removed_token_usage={result['removed_token_usage']}, "
                f"removed_one_time_tasks={result['removed_one_time_tasks']}, "
                f"removed_disabled_periodic_tasks={result['removed_disabled_periodic_tasks']}, "
                f"removed_manual_reply_attachments={result['removed_manual_reply_attachments']}, "
                f"removed_attachment_mappings={result['removed_attachment_mappings']}, "
                f"removed_deleted_bots={result['removed_deleted_bots']}, "
                f"restarted_bots=0, restart_skipped=true"
            ),
        )
    finally:
        pass
    return result


async def run_document_memory_extraction_task(
    database_path: Path,
    project_root: Path,
    task: dict[str, Any],
    trace_id: str = "",
) -> dict[str, Any]:
    prompt_data = json.loads(str(task.get("prompt_text") or "{}"))
    doc_id = prompt_data.get("doc_id", "")
    split_series = prompt_data.get("split_series") or ""
    split_index = int(prompt_data.get("split_index") or 0)
    split_total = int(prompt_data.get("split_total") or 0)

    doc = get_document_by_id(database_path, doc_id)
    if doc is None:
        raise ValueError(f"Document not found: {doc_id}")

    text = prompt_data.get("content", "")
    if not text:
        storage_path = Path(doc["storage_path"])
        if not storage_path.exists():
            raise FileNotFoundError(f"Document file not found: {storage_path}")
        content = storage_path.read_bytes()
        ext = doc["file_type"]
        text = extract_text_from_file(content, ext)

    if not text.strip():
        raise ValueError(f"文档内容为空，无法执行记忆提取: {doc['filename']}")

    from agent_runtime.skills_integration import extract_document_memory

    metadata = {
        "source_id": split_series if split_series else doc_id,
        "title": doc["filename"],
        "filename": doc["filename"],
        "mime_type": doc.get("mime_type", ""),
    }
    mode = "update" if split_index in (0, 1) else "append"

    settings = load_settings_from_database(database_path)
    provider_key, provider_type, model = _resolve_provider_details(settings)
    _log_agent_prompt_payload(
        database_path,
        trace_id=trace_id,
        call_type="document_memory_extraction",
        detail_lines=[
            f"task_key={task.get('task_key', '')}",
            f"doc_id={doc_id}",
            f"filename={doc['filename']}",
            f"split_series={split_series}",
            f"split_index={split_index}",
            f"split_total={split_total}",
            f"text_length={len(text)}",
            f"mode={mode}",
        ],
    )

    result = await extract_document_memory(
        source_text=text,
        metadata=metadata,
        project_root=project_root,
        settings=settings,
        mode=mode,
        split_series=split_series,
        split_index=split_index,
        split_total=split_total,
        database_path=database_path,
    )

    if result.get("ok", False):
        update_document_parse_status(database_path, doc_id, "completed")
        update_document_convert_status(database_path, doc_id, "converted")
    else:
        error_msg = result.get("error", "Unknown error")
        update_document_parse_status(database_path, doc_id, "failed", error=error_msg)
        update_document_convert_status(database_path, doc_id, "failed")

    token_usage = _extract_token_usage(result)
    _record_task_token_usage(
        database_path,
        trace_id=trace_id,
        call_type="document_memory_extraction",
        token_usage=token_usage,
        provider_key=provider_key,
        provider_type=provider_type,
        model=model,
    )
    _log_agent_answer_payload(
        database_path,
        trace_id=trace_id,
        call_type="document_memory_extraction",
        detail_lines=[
            f"ok={bool(result.get('ok', False))}",
            f"summary={str(result.get('summary', '') or '')[:1000]}",
            f"updated_files={json.dumps(result.get('updated_files', []), ensure_ascii=False)}",
            f"token_usage={json.dumps(token_usage, ensure_ascii=False)}",
            f"error={str(result.get('error', '') or '')[:1000]}",
        ],
    )

    notify_bot_key = str(task.get("notify_bot_key") or "").strip()
    if notify_bot_key:
        try:
            _send_task_completion_notification(
                database_path,
                bot_key=notify_bot_key,
                task_key=str(task.get("task_key", "")),
                task_name=str(task.get("task_name", "")),
                call_type="document_memory_extraction",
                ok=bool(result.get("ok", False)),
                summary=str(result.get("summary", "") or ""),
                trace_id=trace_id,
            )
        except Exception:
            logging.getLogger(__name__).exception(
                "任务完成通知发送异常: task_key=%s, bot_key=%s",
                task.get("task_key"), notify_bot_key,
            )

    return {
        "doc_id": doc_id,
        "filename": doc["filename"],
        "split_series": split_series,
        "split_index": split_index,
        "split_total": split_total,
        "extraction_ok": result.get("ok", False),
        "updated_files": result.get("updated_files", []),
        "summary": result.get("summary", ""),
    }


async def run_explicit_memory_task(
    database_path: Path,
    project_root: Path,
    task: dict[str, Any],
    trace_id: str = "",
) -> dict[str, Any]:
    import json as _json
    from app.db.log_store import insert_project_log

    prompt_data = _json.loads(str(task.get("prompt_text") or "{}"))
    source_text = prompt_data.get("source_text", "")
    task_name = str(task.get("task_name") or "记忆生成")

    if not source_text:
        insert_project_log(
            database_path,
            trace_id=trace_id,
            level="ERROR",
            category="task",
            source="explicit_memory",
            message="记忆生成任务失败：无记忆内容",
            detail=f"task_name={task_name}\nreason=prompt_text中无source_text",
        )
        return {"ok": False, "summary": "无记忆内容"}

    insert_project_log(
        database_path,
        trace_id=trace_id,
        level="INFO",
        category="task",
        source="explicit_memory",
        message="记忆生成任务启动",
        detail=(
            f"task_name={task_name}\n"
            f"stage=启动\n"
            f"source_text={source_text[:500]}"
        ),
    )

    from agent_runtime.skills_integration import add_explicit_memory

    settings = load_settings_from_database(database_path)
    provider_key, provider_type, model = _resolve_provider_details(settings)

    insert_project_log(
        database_path,
        trace_id=trace_id,
        level="INFO",
        category="task",
        source="explicit_memory",
        message="记忆生成：调用平台 Agent LLM 提炼中",
        detail=(
            f"task_name={task_name}\n"
            f"stage=LLM提炼\n"
            f"source_text={source_text[:500]}"
        ),
    )
    _log_agent_prompt_payload(
        database_path,
        trace_id=trace_id,
        call_type="explicit_memory",
        detail_lines=[
            f"task_key={task.get('task_key', '')}",
            f"task_name={task_name}",
            f"source_text_length={len(source_text)}",
            f"source_text_preview={source_text[:500]}",
        ],
    )

    result = await add_explicit_memory(
        source_text=source_text,
        project_root=project_root,
        database_path=database_path,
    )

    token_usage = _extract_token_usage(result)
    _record_task_token_usage(
        database_path,
        trace_id=trace_id,
        call_type="explicit_memory",
        token_usage=token_usage,
        provider_key=provider_key,
        provider_type=provider_type,
        model=model,
    )

    ok = result.get("ok", False)
    memory_items = result.get("memory_items", {})
    updated_files = result.get("updated_files", [])
    error = result.get("error", "")
    total = sum(len(v) for v in memory_items.values() if v)

    cat_names = {
        "explicit": "显式记忆",
        "profile": "用户画像",
        "work": "工作事实",
        "document": "文档",
        "timeline": "时间线",
        "inbox": "待确认",
    }

    if ok:
        items_detail_parts = []
        for cat, items in memory_items.items():
            if items and cat != "changelog":
                label = cat_names.get(cat, cat)
                items_detail_parts.append(f"{label}({len(items)}条): " + "; ".join(str(i)[:200] for i in items[:5]))

        insert_project_log(
            database_path,
            trace_id=trace_id,
            level="INFO",
            category="task",
            source="explicit_memory",
            message="记忆生成任务完成",
            detail=(
                f"task_name={task_name}\n"
                f"stage=完成\n"
                f"total={total}\n"
                f"updated_files={', '.join(updated_files)}\n"
                f"items=\n" + "\n".join(items_detail_parts)
            ),
        )
        summary = f"显式记忆生成完成: 成功, {total} 条记忆"
    else:
        insert_project_log(
            database_path,
            trace_id=trace_id,
            level="ERROR",
            category="task",
            source="explicit_memory",
            message="记忆生成任务失败",
            detail=(
                f"task_name={task_name}\n"
                f"stage=失败\n"
                f"source_text={source_text[:500]}\n"
                f"error={str(error)[:1200]}"
            ),
        )
        summary = f"显式记忆生成完成: 失败, {error[:200]}"

    _log_agent_answer_payload(
        database_path,
        trace_id=trace_id,
        call_type="explicit_memory",
        detail_lines=[
            f"ok={ok}",
            f"total={total}",
            f"updated_files={json.dumps(updated_files, ensure_ascii=False)}",
            f"token_usage={json.dumps(token_usage, ensure_ascii=False)}",
            f"error={str(error)[:1000]}",
        ],
    )

    executor_id = str(task.get("executor_id") or "").strip()
    task_key = str(task.get("task_key") or "")
    if executor_id:
        cat_labels = {
            "explicit": "显式记忆",
            "profile": "用户画像",
            "work": "工作事实",
            "timeline": "时间线",
            "inbox": "待确认",
        }
        notify_details = []
        if source_text:
            preview = source_text.strip().replace("\n", " ")[:80]
            notify_details.append(f"📝 原文: {preview}")
        if memory_items:
            for cat, items in memory_items.items():
                if not items or cat == "changelog":
                    continue
                label = cat_labels.get(cat, cat)
                for item in items[:3]:
                    item_content = ""
                    if isinstance(item, dict):
                        item_content = str(item.get("content", ""))
                    else:
                        item_content = str(item)
                    item_content = item_content.strip().replace("\n", " ")[:100]
                    if item_content:
                        notify_details.append(f"{label}: {item_content}")
        _send_task_completion_notification(
            database_path,
            bot_key=executor_id,
            task_key=task_key,
            task_name=task_name,
            call_type="explicit_memory",
            ok=ok,
            summary=summary,
            trace_id=trace_id,
            detail_lines=notify_details,
        )

    return {
        "ok": ok,
        "total": total,
        "memory_items": memory_items,
        "updated_files": updated_files,
        "summary": summary,
    }


def _enrich_feedback_samples_from_audits(
    feedback_samples: list[dict[str, Any]],
    audit_samples: list[dict[str, Any]],
) -> None:
    """将 feedback 样本与 memory_usage_audits 关联，填充 memory_pack 等调用链信息。"""
    # 按 chat_id + bot_key 建立审计索引
    audit_index: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for audit in audit_samples:
        chat_id = str(audit.get("chat_id") or "").strip()
        bot_key = str(audit.get("bot_key") or "").strip()
        if chat_id and bot_key:
            audit_index.setdefault((chat_id, bot_key), []).append(audit)

    for sample in feedback_samples:
        chat_id = str(sample.get("conversation_chat_id") or sample.get("chat_id") or "").strip()
        bot_key = str(sample.get("bot_key") or "").strip()
        msg_id = str(sample.get("msg_id") or "").strip()
        if not chat_id or not bot_key:
            continue
        candidates = audit_index.get((chat_id, bot_key), [])
        if not candidates:
            continue

        question = str(sample.get("question") or "").strip()
        answer_created_at = str(sample.get("answer_created_at") or "").strip()
        feedback_created_at = str(sample.get("created_at") or "").strip()

        def _parse_time(value: str) -> datetime | None:
            text = str(value or "").strip()
            if not text:
                return None
            try:
                return datetime.fromisoformat(text.replace("Z", "+00:00"))
            except ValueError:
                return None

        def _time_distance_seconds(a: str, b: str) -> float | None:
            left = _parse_time(a)
            right = _parse_time(b)
            if left is None or right is None:
                return None
            return abs((left - right).total_seconds())

        def _is_trace_related(audit: dict[str, Any]) -> bool:
            if not msg_id:
                return False
            trace_id = str(audit.get("trace_id") or "")
            return msg_id in trace_id or trace_id.endswith(msg_id)

        # 优先按 trace/msg_id 关联，其次按问题文本，最后按回答/反馈时间最近。
        best_match = None
        for audit in candidates:
            if _is_trace_related(audit):
                best_match = audit
                break
        if best_match is None:
            for audit in candidates:
                query = str(audit.get("user_query") or "").strip()
                if query and question and query == question:
                    best_match = audit
                    break
        if best_match is None and len(candidates) == 1:
            best_match = candidates[0]
        if best_match is None:
            closest: tuple[float, dict[str, Any]] | None = None
            for audit in candidates:
                audit_time = str(audit.get("updated_at") or audit.get("created_at") or "").strip()
                distance = _time_distance_seconds(audit_time, answer_created_at)
                if distance is None:
                    distance = _time_distance_seconds(audit_time, feedback_created_at)
                if distance is None:
                    continue
                if closest is None or distance < closest[0]:
                    closest = (distance, audit)
            if closest is not None and closest[0] <= 3600:
                best_match = closest[1]
        if best_match is None:
            continue
        sample["memory_pack"] = str(best_match.get("memory_pack") or "")
        sample["selected_files"] = list(best_match.get("selected_files") or [])
        sample["selected_sections"] = list(best_match.get("selected_sections") or [])
        sample["token_budget_used_estimate"] = int(best_match.get("token_budget_used_estimate") or 0)


def _feedback_samples_to_memory_audit_samples(samples: list[dict[str, Any]]) -> list[dict[str, Any]]:
    audit_samples: list[dict[str, Any]] = []
    for sample in samples:
        feedback_id = str(sample.get("id") or "").strip()
        result = str(sample.get("result") or "").strip().lower()
        if not feedback_id or result not in {"useful", "useless"}:
            continue
        is_useless = result == "useless"
        reason = str(sample.get("reason") or "").strip()
        audit_samples.append({
            "trace_id": f"feedback:{feedback_id}",
            "call_type": "feedback_useless" if is_useless else "feedback_useful",
            "status": "failed" if is_useless else "completed",
            "chat_id": str(sample.get("conversation_chat_id") or sample.get("chat_id") or ""),
            "chat_display_name": str(sample.get("chat_display_name") or ""),
            "chat_type": str(sample.get("chat_type") or ""),
            "bot_key": str(sample.get("bot_key") or ""),
            "bot_name": str(sample.get("bot_name") or sample.get("bot_key") or ""),
            "user_query": str(sample.get("question") or ""),
            "final_answer": str(sample.get("answer") or ""),
            "memory_pack": str(sample.get("memory_pack", "") or ""),
            "selected_files": list(sample.get("selected_files") or []),
            "selected_sections": list(sample.get("selected_sections") or []),
            "token_budget_used_estimate": int(sample.get("token_budget_used_estimate") or 0),
            "needs_more_memory": is_useless,
            "confidence": "user_feedback",
            "feedback_id": feedback_id,
            "feedback_result": result,
            "feedback_reason": reason if is_useless else "",
            "feedback_created_at": str(sample.get("created_at") or ""),
            "feedback_user_id": str(sample.get("user_id") or ""),
            "feedback_msg_id": str(sample.get("msg_id") or ""),
            "feedback_note": "用户明确标记该回复无用，反馈原因是 Agent 复盘和记忆审核的优先参考方向。" if is_useless else "用户标记该回复有用，可作为记忆质量正面参考。",
        })
    return audit_samples


async def run_self_review_chat_memory_task(
    database_path: Path,
    project_root: Path,
    task: dict[str, Any],
    trace_id: str = "",
) -> dict[str, Any]:
    settings = load_settings_from_database(database_path)
    from agent_runtime.skills_integration import review_memory
    task_prompt, review_mode, review_suggestion = _parse_review_prompt_and_mode(task)

    # 将用户审核建议注入到提示词中
    if review_suggestion:
        task_prompt = f"{task_prompt.rstrip()}\n\n【重点参照的审核方向】\n{review_suggestion}"

    memory_usage_samples = list_recent_memory_usage_audits(
        database_path,
        days=7,
        call_types=("chat", "draft"),
        limit=80,
    )
    useless_feedback_samples = list_recent_feedback_review_samples(
        database_path,
        result="useless",
        days=7,
        limit=40,
    )
    useful_feedback_samples = list_recent_feedback_review_samples(
        database_path,
        result="useful",
        days=7,
        limit=20,
        exclude_reviewed=False,
    )
    # 用审计记录丰富反馈样本的调用链信息
    _enrich_feedback_samples_from_audits(useless_feedback_samples, memory_usage_samples)
    _enrich_feedback_samples_from_audits(useful_feedback_samples, memory_usage_samples)
    audit_samples = [
        *_feedback_samples_to_memory_audit_samples(useless_feedback_samples),
        *memory_usage_samples,
        *_feedback_samples_to_memory_audit_samples(useful_feedback_samples),
    ]
    if not audit_samples:
        raise ValueError("无会话记忆使用记录或用户反馈记录，无法执行审查")
    _log_agent_prompt_payload(
        database_path,
        trace_id=trace_id,
        call_type="self_review_chat_memory",
        detail_lines=[
            f"task_key={task.get('task_key', '')}",
            "review_type=conversation_usage",
            "usage_scope=chat",
            f"review_mode={review_mode}",
            f"audit_samples={len(audit_samples)}",
            f"memory_usage_samples={len(memory_usage_samples)}",
            f"useless_feedback_samples={len(useless_feedback_samples)}",
            f"useful_feedback_samples={len(useful_feedback_samples)}",
            f"review_prompt={task_prompt[:1000]}",
        ],
    )
    result = await review_memory(
        project_root=project_root,
        settings=settings,
        database_path=database_path,
        review_type="conversation_usage",
        audit_payload=audit_samples,
        usage_scope="chat",
        mode=review_mode,
        review_prompt=task_prompt,
    )

    ok = bool(result.get("ok", False))
    if ok:
        # 标记 reviewer 确认已审核的反馈记录。负反馈根因审查失败时不消费，后续继续优先复盘。
        reviewed_feedback_ids = [
            fid
            for fid in (str(item or "").strip() for item in result.get("reviewed_feedback_ids", []))
            if fid
        ]
        if reviewed_feedback_ids:
            try:
                from app.db.feedback_store import mark_feedbacks_reviewed
                mark_feedbacks_reviewed(database_path, reviewed_feedback_ids)
            except Exception:
                logging.getLogger(__name__).exception("标记反馈已审核失败")

    quality_score = result.get("quality_score", 0)
    issues_count = len(result.get("issues", []))
    patches_count = len(result.get("recommended_patches", []))
    counters = result.get("usage_counters", {}) or {}
    error_text = str(result.get("error", "") or "").strip()
    patch_results = result.get("patch_results", {}) or {}
    applied_patch_count = len(patch_results.get("applied", []) or [])
    skipped_patch_count = len(patch_results.get("skipped", []) or [])
    patch_error_count = len(patch_results.get("errors", []) or [])
    applied_note = ""
    if review_mode == "patch" and patches_count > 0:
        applied_note = f", 已自动应用 {applied_patch_count} 个补丁"
        if skipped_patch_count or patch_error_count:
            applied_note += f"（跳过 {skipped_patch_count}, 错误 {patch_error_count}）"
    elif review_mode == "review" and patches_count > 0:
        applied_note = f", 建议补丁 {patches_count} 个未应用"
    if ok:
        summary = (
            f"会话记忆审查完成: 质量分 {quality_score}, 问题 {issues_count}, 补丁 {patches_count}{applied_note}, "
            f"有效 {counters.get('used_effectively', 0)}, 浪费 {counters.get('used_but_wasteful', 0)}, "
            f"漏召回 {counters.get('needed_but_missed', 0)}, 无关注入 {counters.get('irrelevant_injection', 0)}, "
            f"优先级违规 {counters.get('priority_violation', 0)}, 预算超限 {counters.get('budget_overrun', 0)}, "
            f"用户无用反馈 {counters.get('feedback_useless', 0)}, 用户有用反馈 {counters.get('feedback_useful', 0)}, "
            f"无用反馈根因审查 {counters.get('feedback_useless_reviewed', 0)}, "
            f"根因审查失败 {counters.get('feedback_useless_review_failed', 0)}"
        )
    else:
        summary = f"会话记忆审查失败: {error_text[:500] or 'unknown error'}"
    insert_project_log(
        database_path,
        trace_id=trace_id,
        level="INFO",
        category="task",
        source="self_review_chat_memory",
        message="Chat memory review completed",
        detail=summary,
    )
    token_usage = _extract_token_usage(result)
    provider_key, provider_type, model = _resolve_provider_details(settings)
    _record_task_token_usage(
        database_path,
        trace_id=trace_id,
        call_type="self_review_chat_memory",
        token_usage=token_usage,
        provider_key=provider_key,
        provider_type=provider_type,
        model=model,
    )
    _log_task_token_usage_payload(
        database_path,
        trace_id=trace_id,
        call_type="self_review_chat_memory",
        token_usage=token_usage,
        provider_key=provider_key,
        provider_type=provider_type,
        model=model,
    )
    _log_agent_answer_payload(
        database_path,
        trace_id=trace_id,
        call_type="self_review_chat_memory",
        detail_lines=[
            f"ok={ok}",
            f"quality_score={quality_score}",
            f"reviewed_samples={int(result.get('reviewed_samples', 0) or 0)}",
            f"issues_count={issues_count}",
            f"patches_count={patches_count}",
            f"report_path={str(result.get('report_path', '') or '')}",
            f"token_usage={json.dumps(token_usage, ensure_ascii=False)}",
            f"review_summary={str(result.get('review_summary', '') or '')[:2000]}",
            f"usage_counters={_json_preview(counters, 3000)}",
            f"issues_preview={_json_preview(result.get('issues', []), 12000)}",
            f"recommended_patches_preview={_json_preview(result.get('recommended_patches', []), 12000)}",
            f"suspicious_samples_preview={_json_preview(result.get('suspicious_samples', []), 12000)}",
            f"reviewed_sample_details_preview={_json_preview(result.get('reviewed_sample_details', []), 20000)}",
            f"review_traces_preview={_json_preview(result.get('review_traces', []), 12000)}",
            f"error={str(result.get('error', '') or '')[:1000]}",
        ],
    )

    notify_bot_key = str(task.get("notify_bot_key") or "").strip()
    if notify_bot_key:
        try:
            _send_task_completion_notification(
                database_path,
                bot_key=notify_bot_key,
                task_key=str(task.get("task_key", "")),
                task_name=str(task.get("task_name", "")),
                call_type="self_review_chat_memory",
                ok=ok,
                summary=summary,
                trace_id=trace_id,
            )
        except Exception:
            logging.getLogger(__name__).exception(
                "任务完成通知发送异常: task_key=%s, bot_key=%s",
                task.get("task_key"), notify_bot_key,
            )

    return {
        "ok": ok,
        "quality_score": quality_score,
        "issues_count": issues_count,
        "patches_count": patches_count,
        "reviewed_samples": int(result.get("reviewed_samples", 0) or 0),
        "usage_counters": counters,
        "report_path": str(result.get("report_path", "") or ""),
        "token_usage": token_usage,
        "summary": summary,
    }


async def run_self_review_document_memory_task(
    database_path: Path,
    project_root: Path,
    task: dict[str, Any],
    trace_id: str = "",
) -> dict[str, Any]:
    settings = load_settings_from_database(database_path)
    from agent_runtime.skills_integration import review_memory
    task_prompt, review_mode, review_suggestion = _parse_review_prompt_and_mode(task)

    # 将用户审核建议注入到提示词中
    if review_suggestion:
        task_prompt = f"{task_prompt.rstrip()}\n\n【重点参照的审核方向】\n{review_suggestion}"

    audit_samples = list_recent_memory_usage_audits(
        database_path,
        days=7,
        call_types=("chat", "draft"),
        limit=80,
        require_documents=True,
    )
    if not audit_samples:
        summary = "文档记忆审查失败: 无文档记忆使用记录，无法执行审查"
        insert_project_log(
            database_path,
            trace_id=trace_id,
            level="WARNING",
            category="task",
            source="self_review_document_memory",
            message="Document memory review skipped",
            detail=summary,
        )
        return {
            "ok": False,
            "quality_score": 0,
            "issues_count": 0,
            "patches_count": 0,
            "reviewed_samples": 0,
            "usage_counters": {},
            "report_path": "",
            "summary": summary,
            "error": "无文档记忆使用记录，无法执行审查",
        }
    _log_agent_prompt_payload(
        database_path,
        trace_id=trace_id,
        call_type="self_review_document_memory",
        detail_lines=[
            f"task_key={task.get('task_key', '')}",
            "review_type=conversation_usage",
            "usage_scope=document",
            f"review_mode={review_mode}",
            f"audit_samples={len(audit_samples)}",
            f"review_prompt={task_prompt[:1000]}",
        ],
    )
    result = await review_memory(
        project_root=project_root,
        settings=settings,
        database_path=database_path,
        review_type="conversation_usage",
        audit_payload=audit_samples,
        usage_scope="document",
        mode=review_mode,
        review_prompt=task_prompt,
    )

    ok = bool(result.get("ok", False))
    quality_score = result.get("quality_score", 0)
    issues_count = len(result.get("issues", []))
    patches_count = len(result.get("recommended_patches", []))
    counters = result.get("usage_counters", {}) or {}
    error_text = str(result.get("error", "") or "").strip()
    patch_results = result.get("patch_results", {}) or {}
    applied_patch_count = len(patch_results.get("applied", []) or [])
    skipped_patch_count = len(patch_results.get("skipped", []) or [])
    patch_error_count = len(patch_results.get("errors", []) or [])
    applied_note = ""
    if review_mode == "patch" and patches_count > 0:
        applied_note = f", 已自动应用 {applied_patch_count} 个补丁"
        if skipped_patch_count or patch_error_count:
            applied_note += f"（跳过 {skipped_patch_count}, 错误 {patch_error_count}）"
    elif review_mode == "review" and patches_count > 0:
        applied_note = f", 建议补丁 {patches_count} 个未应用"
    if ok:
        summary = (
            f"文档记忆审查完成: 质量分 {quality_score}, 问题 {issues_count}, 补丁 {patches_count}{applied_note}, "
            f"有效 {counters.get('used_effectively', 0)}, 浪费 {counters.get('used_but_wasteful', 0)}, "
            f"漏召回 {counters.get('needed_but_missed', 0)}, 无关注入 {counters.get('irrelevant_injection', 0)}, "
            f"优先级违规 {counters.get('priority_violation', 0)}, 预算超限 {counters.get('budget_overrun', 0)}"
        )
    else:
        summary = f"文档记忆审查失败: {error_text[:500] or 'unknown error'}"
    insert_project_log(
        database_path,
        trace_id=trace_id,
        level="INFO",
        category="task",
        source="self_review_document_memory",
        message="Document memory review completed",
        detail=summary,
    )
    token_usage = _extract_token_usage(result)
    provider_key, provider_type, model = _resolve_provider_details(settings)
    _record_task_token_usage(
        database_path,
        trace_id=trace_id,
        call_type="self_review_document_memory",
        token_usage=token_usage,
        provider_key=provider_key,
        provider_type=provider_type,
        model=model,
    )
    _log_task_token_usage_payload(
        database_path,
        trace_id=trace_id,
        call_type="self_review_document_memory",
        token_usage=token_usage,
        provider_key=provider_key,
        provider_type=provider_type,
        model=model,
    )
    _log_agent_answer_payload(
        database_path,
        trace_id=trace_id,
        call_type="self_review_document_memory",
        detail_lines=[
            f"ok={ok}",
            f"quality_score={quality_score}",
            f"reviewed_samples={int(result.get('reviewed_samples', 0) or 0)}",
            f"issues_count={issues_count}",
            f"patches_count={patches_count}",
            f"report_path={str(result.get('report_path', '') or '')}",
            f"token_usage={json.dumps(token_usage, ensure_ascii=False)}",
            f"review_summary={str(result.get('review_summary', '') or '')[:2000]}",
            f"usage_counters={_json_preview(counters, 3000)}",
            f"issues_preview={_json_preview(result.get('issues', []), 12000)}",
            f"recommended_patches_preview={_json_preview(result.get('recommended_patches', []), 12000)}",
            f"suspicious_samples_preview={_json_preview(result.get('suspicious_samples', []), 12000)}",
            f"reviewed_sample_details_preview={_json_preview(result.get('reviewed_sample_details', []), 20000)}",
            f"review_traces_preview={_json_preview(result.get('review_traces', []), 12000)}",
            f"error={str(result.get('error', '') or '')[:1000]}",
        ],
    )

    notify_bot_key = str(task.get("notify_bot_key") or "").strip()
    if notify_bot_key:
        try:
            _send_task_completion_notification(
                database_path,
                bot_key=notify_bot_key,
                task_key=str(task.get("task_key", "")),
                task_name=str(task.get("task_name", "")),
                call_type="self_review_document_memory",
                ok=ok,
                summary=summary,
                trace_id=trace_id,
            )
        except Exception:
            logging.getLogger(__name__).exception(
                "任务完成通知发送异常: task_key=%s, bot_key=%s",
                task.get("task_key"), notify_bot_key,
            )

    return {
        "ok": ok,
        "quality_score": quality_score,
        "issues_count": issues_count,
        "patches_count": patches_count,
        "reviewed_samples": int(result.get("reviewed_samples", 0) or 0),
        "usage_counters": counters,
        "report_path": str(result.get("report_path", "") or ""),
        "token_usage": token_usage,
        "summary": summary,
    }


def _clean_and_format_qa_pairs(messages: Any) -> str:
    qa_pairs: list[str] = []

    if isinstance(messages, dict) and "chats" in messages:
        chat_list = messages["chats"]
        if isinstance(chat_list, dict):
            normalized_chat_list = []
            for chat_id, chat_data in chat_list.items():
                if isinstance(chat_data, dict):
                    normalized = dict(chat_data)
                    normalized.setdefault("chat_id", str(chat_id))
                    normalized_chat_list.append(normalized)
            chat_list = normalized_chat_list
        elif not isinstance(chat_list, list):
            chat_list = []
        for chat in chat_list:
            if not isinstance(chat, dict):
                continue
            chat_display = str(chat.get("chat_display_name") or chat.get("display_name") or "").strip()
            chat_type = str(chat.get("chat_type") or "").strip()
            is_group = chat_type in ("group", "room")
            chat_label = f"群聊[{chat_display}]" if is_group and chat_display else (f"用户[{chat_display}]" if chat_display else "")
            if "pairs" in chat and isinstance(chat["pairs"], list):
                for pair in chat["pairs"]:
                    if is_ai_auto_reply_pair(pair) and not is_user_confirmed_ai_pair(pair):
                        continue
                    q = str(pair.get("question") or "").strip()
                    a = str(pair.get("answer") or "").strip()
                    if not q or not a:
                        continue
                    q_user = str(pair.get("question_sender") or "用户").strip() or "用户"
                    a_direction = str(pair.get("direction") or "bot").strip()
                    q_time = str(pair.get("question_time") or pair.get("time") or "").strip()
                    a_time = str(pair.get("answer_time") or pair.get("time") or "").strip()
                    if a_direction == "manual":
                        a_label = "助理(人工/草稿)"
                    elif is_user_confirmed_ai_pair(pair):
                        a_label = "助理(AI/用户标记有用)"
                    else:
                        a_label = "助理(AI)"
                    q_time_label = f"[{q_time}]" if q_time else ""
                    a_time_label = f"[{a_time}]" if a_time else q_time_label
                    chat_tag = f"[{chat_label}]" if chat_label else ""
                    feedback_result = str(pair.get("answer_feedback_result") or "").strip().lower()
                    feedback_reason = str(pair.get("answer_feedback_reason") or "").strip()
                    if feedback_result == "useful":
                        feedback_line = "\n用户反馈: useful"
                    elif feedback_result == "useless":
                        feedback_line = f"\n用户反馈: useless（原因：{feedback_reason}）" if feedback_reason else "\n用户反馈: useless"
                    else:
                        feedback_line = ""
                    qa_pairs.append(f"{q_time_label} {chat_tag} {q_user}: {q}\n{a_time_label} {chat_tag} {a_label}: {a}{feedback_line}")
        return "\n\n".join(qa_pairs)

    return ""


def _collect_message_ids_from_mapping(value: Any) -> list[str]:
    result: list[str] = []
    if not isinstance(value, dict):
        return result
    for msg_ids in value.values():
        if not isinstance(msg_ids, list):
            continue
        for msg_id in msg_ids:
            text = str(msg_id or "").strip()
            if text:
                result.append(text)
    return _dedupe_preserve_order(result)


def _dedupe_preserve_order(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value in seen:
            continue
        seen.add(value)
        result.append(value)
    return result


async def run_memory_update_task(
    database_path: Path,
    project_root: Path,
    task: dict[str, Any],
    trace_id: str = "",
) -> dict[str, Any]:
    all_msg_ids_to_mark = []
    extraction_msg_ids_to_mark = []
    skipped_msg_ids_to_mark = []
    messages_to_process = None
    cutoff_time = ""
    custom_prompt = task.get("prompt_text")
    if custom_prompt:
        try:
            prompt_data = json.loads(custom_prompt)
            cutoff_time = str(prompt_data.get("cutoff_time") or "").strip()
            if "extraction_message_ids" in prompt_data and isinstance(prompt_data["extraction_message_ids"], dict):
                extraction_msg_ids_to_mark.extend(_collect_message_ids_from_mapping(prompt_data["extraction_message_ids"]))
            if "skipped_ai_message_ids" in prompt_data and isinstance(prompt_data["skipped_ai_message_ids"], dict):
                skipped_msg_ids_to_mark.extend(_collect_message_ids_from_mapping(prompt_data["skipped_ai_message_ids"]))
            all_msg_ids_to_mark = _dedupe_preserve_order(extraction_msg_ids_to_mark + skipped_msg_ids_to_mark)
            if all_msg_ids_to_mark:
                insert_project_log(
                    database_path,
                    trace_id=trace_id,
                    level="INFO",
                    category="task",
                    source="task_runtime",
                    message="从原始数据中收集消息ID",
                    detail=(
                        f"mark_candidate_message_count={len(all_msg_ids_to_mark)}\n"
                        f"extraction_message_count={len(_dedupe_preserve_order(extraction_msg_ids_to_mark))}\n"
                        f"skipped_message_count={len(_dedupe_preserve_order(skipped_msg_ids_to_mark))}"
                    ),
                )
            if "chats" in prompt_data:
                messages_to_process = prompt_data
                insert_project_log(
                    database_path,
                    trace_id=trace_id,
                    level="INFO",
                    category="task",
                    source="task_runtime",
                    message="使用新格式的会话消息数据",
                    detail=f"custom_chats_count={len(prompt_data['chats'])}",
                )
        except (json.JSONDecodeError, Exception):
            pass

    if messages_to_process is None:
        preview = build_memory_update_preview(database_path)
        extraction_msg_ids_to_mark.extend(_collect_message_ids_from_mapping(preview.get("extraction_message_ids") or {}))
        skipped_msg_ids_to_mark.extend(_collect_message_ids_from_mapping(preview.get("skipped_ai_message_ids") or {}))
        all_msg_ids_to_mark = _dedupe_preserve_order(extraction_msg_ids_to_mark + skipped_msg_ids_to_mark)
        all_msg_ids_to_mark = _dedupe_preserve_order(all_msg_ids_to_mark)
        if int(preview.get("selected_message_count", 0) or 0) == 0 and int(preview.get("omitted_message_count", 0) or 0) == 0:
            if all_msg_ids_to_mark:
                await asyncio.to_thread(mark_messages_converted, database_path, all_msg_ids_to_mark)
                skipped_ai_pair_count = int(preview.get("skipped_ai_pair_count", 0) or 0)
                skipped_ai_message_count = int(preview.get("skipped_ai_message_count", 0) or 0)
                skipped_useless_ai_pair_count = int(preview.get("skipped_useless_ai_pair_count", 0) or 0)
                summary = (
                    "没有可进入记忆提取的人工/草稿/useful AI 回复会话；"
                    f"已跳过 {skipped_ai_pair_count} 组 AI 自动回复 QA、"
                    f"{skipped_ai_message_count} 条 AI 自动回复相关消息，"
                    f"其中 useless 反馈 {skipped_useless_ai_pair_count} 组，"
                    f"并标记 {len(all_msg_ids_to_mark)} 条消息为已转换"
                )
                insert_project_log(
                    database_path,
                    trace_id=trace_id,
                    level="INFO",
                    category="task",
                    source="task_runtime",
                    message="已跳过 AI 自动回复会话并更新转换状态",
                    detail=(
                        f"skipped_ai_pair_count={skipped_ai_pair_count}\n"
                        f"skipped_ai_message_count={skipped_ai_message_count}\n"
                        f"skipped_useless_ai_pair_count={skipped_useless_ai_pair_count}\n"
                        f"marked_message_count={len(all_msg_ids_to_mark)}"
                    ),
                )
                return {
                    "chats_processed": 0,
                    "success_count": 0,
                    "fail_count": 0,
                    "marked_messages": len(all_msg_ids_to_mark),
                    "skipped_ai_pair_count": skipped_ai_pair_count,
                    "skipped_ai_message_count": skipped_ai_message_count,
                    "skipped_useless_ai_pair_count": skipped_useless_ai_pair_count,
                    "summary": summary,
                }
            raise ValueError("无未转换的聊天记录，无法执行记忆更新")
        if preview.get("is_truncated"):
            _truncated_summary = (
                "聊天记录超过单次记忆更新限制，已暂停自动执行。"
                f" 当前批次 {preview.get('selected_pair_count', 0)} 组问答、"
                f"{preview.get('selected_message_count', 0)} 条消息，剩余 "
                f"{preview.get('omitted_pair_count', 0)} 组问答、"
                f"{preview.get('omitted_message_count', 0)} 条消息待人工处理。"
                f" 已从会话列表排除 {preview.get('skipped_ai_pair_count', 0)} 组 AI 自动回复 QA，"
                f"本批纳入 {preview.get('included_useful_ai_pair_count', 0)} 组 useful AI QA。"
            )
            notify_bot_key = str(task.get("notify_bot_key") or "").strip()
            if notify_bot_key:
                try:
                    _send_task_completion_notification(
                        database_path,
                        bot_key=notify_bot_key,
                        task_key=str(task.get("task_key", "")),
                        task_name=str(task.get("task_name", "")),
                        call_type="memory_update",
                        ok=False,
                        summary=_truncated_summary,
                        trace_id=trace_id,
                    )
                except Exception:
                    logging.getLogger(__name__).exception(
                        "任务完成通知发送异常: task_key=%s, bot_key=%s",
                        task.get("task_key"), notify_bot_key,
                    )
            return {
                "ok": False,
                "requires_manual_review": True,
                "prompt_payload": preview.get("payload") or {},
                "selected_pair_count": int(preview.get("selected_pair_count", 0) or 0),
                "selected_message_count": int(preview.get("selected_message_count", 0) or 0),
                "omitted_pair_count": int(preview.get("omitted_pair_count", 0) or 0),
                "omitted_message_count": int(preview.get("omitted_message_count", 0) or 0),
                "skipped_ai_pair_count": int(preview.get("skipped_ai_pair_count", 0) or 0),
                "skipped_ai_message_count": int(preview.get("skipped_ai_message_count", 0) or 0),
                "included_useful_ai_pair_count": int(preview.get("included_useful_ai_pair_count", 0) or 0),
                "included_useful_ai_message_count": int(preview.get("included_useful_ai_message_count", 0) or 0),
                "summary": _truncated_summary,
            }
        messages_to_process = preview.get("payload")
        cutoff_time = str(preview.get("cutoff_time") or "").strip()

    if not messages_to_process:
        skipped_msg_ids_to_mark = _dedupe_preserve_order(skipped_msg_ids_to_mark)
        if skipped_msg_ids_to_mark:
            await asyncio.to_thread(mark_messages_converted, database_path, skipped_msg_ids_to_mark)
        raise ValueError("无未转换的聊天记录，无法执行记忆更新")

    settings = load_settings_from_database(database_path)
    provider_key, provider_type, model = _resolve_provider_details(settings)
    from agent_runtime.skills_integration import extract_chat_memory

    success_count = 0
    fail_count = 0

    qa_text = _clean_and_format_qa_pairs(messages_to_process)
    if qa_text.strip():
        _log_agent_prompt_payload(
            database_path,
            trace_id=trace_id,
            call_type="memory_update",
            detail_lines=[
                f"task_key={task.get('task_key', '')}",
                f"cutoff_time={cutoff_time}",
                f"qa_text_length={len(qa_text)}",
                f"message_count={len(all_msg_ids_to_mark)}",
                f"skipped_ai_pair_count={messages_to_process.get('skipped_ai_pair_count', 0) if isinstance(messages_to_process, dict) else 0}",
                f"skipped_ai_message_count={messages_to_process.get('skipped_ai_message_count', 0) if isinstance(messages_to_process, dict) else 0}",
                f"included_useful_ai_pair_count={messages_to_process.get('included_useful_ai_pair_count', 0) if isinstance(messages_to_process, dict) else 0}",
                f"included_useful_ai_message_count={messages_to_process.get('included_useful_ai_message_count', 0) if isinstance(messages_to_process, dict) else 0}",
                f"qa_preview={qa_text[:1200]}",
            ],
        )
        chat_contexts = []
        if isinstance(messages_to_process, dict) and "chats" in messages_to_process:
            chat_items = messages_to_process["chats"]
            if isinstance(chat_items, dict):
                chat_iterable = []
                for chat_id, chat_data in chat_items.items():
                    if isinstance(chat_data, dict):
                        normalized = dict(chat_data)
                        normalized.setdefault("chat_id", str(chat_id))
                        chat_iterable.append(normalized)
            elif isinstance(chat_items, list):
                chat_iterable = chat_items
            else:
                chat_iterable = []
            for chat in chat_iterable:
                if isinstance(chat, dict):
                    chat_contexts.append({
                        "chat_id": str(chat.get("chat_id") or ""),
                        "chat_display_name": str(chat.get("chat_display_name") or chat.get("display_name") or ""),
                        "chat_type": str(chat.get("chat_type") or ""),
                    })
        metadata = {
            "source_id": "memory_update",
            "title": "Memory Update",
            "chats": chat_contexts,
        }
        result = await extract_chat_memory(
            source_text=qa_text,
            metadata=metadata,
            project_root=project_root,
            settings=settings,
            database_path=database_path,
        )
        if result.get("ok", False):
            success_count += 1
        else:
            fail_count += 1
        token_usage = _extract_token_usage(result)
        _record_task_token_usage(
            database_path,
            trace_id=trace_id,
            call_type="memory_update",
            token_usage=token_usage,
            provider_key=provider_key,
            provider_type=provider_type,
            model=model,
        )
        _log_agent_answer_payload(
            database_path,
            trace_id=trace_id,
            call_type="memory_update",
            detail_lines=[
                f"ok={bool(result.get('ok', False))}",
                f"summary={str(result.get('summary', '') or '')[:1000]}",
                f"updated_files={json.dumps(result.get('updated_files', []), ensure_ascii=False)}",
                f"token_usage={json.dumps(token_usage, ensure_ascii=False)}",
                f"error={str(result.get('error', '') or '')[:1000]}",
            ],
        )

    extraction_msg_ids_to_mark = _dedupe_preserve_order(extraction_msg_ids_to_mark)
    skipped_msg_ids_to_mark = _dedupe_preserve_order(skipped_msg_ids_to_mark)
    if fail_count == 0:
        marked_msg_ids = _dedupe_preserve_order(extraction_msg_ids_to_mark + skipped_msg_ids_to_mark)
        retained_msg_ids = []
    else:
        marked_msg_ids = skipped_msg_ids_to_mark
        retained_msg_ids = extraction_msg_ids_to_mark

    if marked_msg_ids:
        await asyncio.to_thread(mark_messages_converted, database_path, marked_msg_ids)
        insert_project_log(
            database_path,
            trace_id=trace_id,
            level="INFO",
            category="task",
            source="task_runtime",
            message="已更新消息转换状态",
            detail=(
                f"marked_message_count={len(marked_msg_ids)}\n"
                f"retained_message_count={len(retained_msg_ids)}\n"
                f"fail_count={fail_count}"
            ),
        )

    skipped_ai_pair_count = int(messages_to_process.get("skipped_ai_pair_count", 0) or 0) if isinstance(messages_to_process, dict) else 0
    skipped_ai_message_count = int(messages_to_process.get("skipped_ai_message_count", 0) or 0) if isinstance(messages_to_process, dict) else 0
    included_useful_ai_pair_count = int(messages_to_process.get("included_useful_ai_pair_count", 0) or 0) if isinstance(messages_to_process, dict) else 0
    included_useful_ai_message_count = int(messages_to_process.get("included_useful_ai_message_count", 0) or 0) if isinstance(messages_to_process, dict) else 0
    skipped_summary = (
        f"；跳过 AI 自动回复 {skipped_ai_pair_count} 组/{skipped_ai_message_count} 条"
        if skipped_ai_pair_count or skipped_ai_message_count
        else ""
    )
    useful_ai_summary = (
        f"；纳入 useful AI 回复 {included_useful_ai_pair_count} 组/{included_useful_ai_message_count} 条"
        if included_useful_ai_pair_count or included_useful_ai_message_count
        else ""
    )
    retained_summary = f"；保留 {len(retained_msg_ids)} 条待提取消息供重试" if retained_msg_ids else ""
    summary = f"处理会话，成功 {success_count}，失败 {fail_count}{skipped_summary}{useful_ai_summary}；标记 {len(marked_msg_ids)} 条消息为已转换{retained_summary}"
    if fail_count == 0 and cutoff_time:
        remaining_preview = build_memory_update_preview(database_path, cutoff_time=cutoff_time)
        remaining_selected_messages = int(remaining_preview.get("selected_message_count", 0) or 0)
        if remaining_selected_messages > 0:
            _batch_summary = (
                f"{summary}。仍有 {remaining_preview.get('selected_pair_count', 0)} 组问答、"
                f"{remaining_selected_messages} 条消息未处理，已等待人工继续下一批。"
            )
            notify_bot_key = str(task.get("notify_bot_key") or "").strip()
            if notify_bot_key:
                try:
                    _send_task_completion_notification(
                        database_path,
                        bot_key=notify_bot_key,
                        task_key=str(task.get("task_key", "")),
                        task_name=str(task.get("task_name", "")),
                        call_type="memory_update",
                        ok=True,
                        summary=_batch_summary,
                        trace_id=trace_id,
                    )
                except Exception:
                    logging.getLogger(__name__).exception(
                        "任务完成通知发送异常: task_key=%s, bot_key=%s",
                        task.get("task_key"), notify_bot_key,
                    )
            return {
                "chats_processed": len((messages_to_process.get("chats") or {})) if isinstance(messages_to_process, dict) else 0,
                "success_count": success_count,
                "fail_count": fail_count,
                "marked_messages": len(marked_msg_ids),
                "retained_messages": len(retained_msg_ids),
                "next_batch_required": True,
                "prompt_payload": remaining_preview.get("payload") or {},
                "pending_pair_count": int(remaining_preview.get("selected_pair_count", 0) or 0),
                "pending_message_count": remaining_selected_messages,
                "included_useful_ai_pair_count": included_useful_ai_pair_count,
                "included_useful_ai_message_count": included_useful_ai_message_count,
                "summary": _batch_summary,
            }
    chats_processed = 0
    if isinstance(messages_to_process, dict):
        chat_items = messages_to_process.get("chats", [])
        if isinstance(chat_items, dict):
            chats_processed = len(chat_items)
        elif isinstance(chat_items, list):
            chats_processed = len(chat_items)

    notify_bot_key = str(task.get("notify_bot_key") or "").strip()
    if notify_bot_key:
        try:
            _send_task_completion_notification(
                database_path,
                bot_key=notify_bot_key,
                task_key=str(task.get("task_key", "")),
                task_name=str(task.get("task_name", "")),
                call_type="memory_update",
                ok=fail_count == 0,
                summary=summary,
                trace_id=trace_id,
            )
        except Exception:
            logging.getLogger(__name__).exception(
                "任务完成通知发送异常: task_key=%s, bot_key=%s",
                task.get("task_key"), notify_bot_key,
            )

    return {
        "chats_processed": chats_processed,
        "success_count": success_count,
        "fail_count": fail_count,
        "marked_messages": len(marked_msg_ids),
        "retained_messages": len(retained_msg_ids),
        "included_useful_ai_pair_count": included_useful_ai_pair_count,
        "included_useful_ai_message_count": included_useful_ai_message_count,
        "summary": summary,
    }


async def run_bot_task(
    database_path: Path,
    project_root: Path,
    task: dict[str, Any],
    trace_id: str = "",
) -> dict[str, Any]:
    """执行 bot_task：通过 Bot 的 Agent 执行用户选择的 Skill 和 MCP，最后用 notify-me 通知结果"""
    import uuid
    from app.db.log_store import insert_project_log

    task_key = str(task.get("task_key", ""))
    task_name = str(task.get("task_name", "未知任务"))
    executor_id = str(task.get("executor_id", ""))
    is_one_time = str(task.get("task_type", "")) == "one_time"
    effective_trace_id = trace_id or str(uuid.uuid4().hex)

    # 1. 解析 prompt_text
    prompt_data = _parse_bot_task_prompt_data(task.get("prompt_text"))
    user_prompt = str(prompt_data.get("user_prompt", ""))
    skill_names = prompt_data.get("skill_names", [])
    mcp_server_ids = prompt_data.get("mcp_server_ids", [])

    insert_project_log(
        database_path,
        trace_id=trace_id,
        level="INFO",
        category="task",
        source="bot_task",
        message=f"bot_task 启动：{task_name}",
        detail=(
            f"task_key={task_key}\n"
            f"task_type={'一次性' if is_one_time else '周期'}\n"
            f"executor_id={executor_id}\n"
            f"user_prompt={user_prompt[:500]}\n"
            f"skill_names={skill_names}\n"
            f"mcp_server_ids={mcp_server_ids}"
        ),
    )

    # 2. 检查 Bot 是否在线
    from app.bot_process_manager import BotProcessManager
    manager = BotProcessManager(project_root)
    bot_status = manager.status(executor_id)
    if not bool(bot_status.get("running")):
        error_msg = f"Bot 不在线，请先启动 Bot 后重试：{executor_id}"
        insert_project_log(
            database_path,
            trace_id=trace_id,
            level="ERROR",
            category="task",
            source="bot_task",
            message=f"bot_task 失败：{task_name} - Bot 不在线",
            detail=error_msg,
        )
        return {
            "ok": False,
            "summary": error_msg,
        }

    # 3. 加载 Bot 的 Settings
    settings = load_settings_from_database(database_path, bot_key=executor_id)

    # 4. 构建 Agent 并执行任务
    insert_project_log(
        database_path,
        trace_id=trace_id,
        level="INFO",
        category="task",
        source="bot_task",
        message=f"bot_task 执行中：{task_name} - 调用 Agent",
        detail=(
            f"stage=Agent执行\n"
            f"user_prompt={user_prompt[:500]}\n"
            f"skill_names={skill_names}\n"
            f"mcp_server_ids={mcp_server_ids}"
        ),
    )

    # 调用 Agent 执行
    from agent_runtime.service import AgentService
    agent_service = AgentService(settings, project_root=project_root)
    agent_service.database_path = database_path

    try:
        result_text, input_tokens, output_tokens = await agent_service.answer_for_task(
            user_prompt.strip() or str(task.get("prompt_text") or "").strip(),
            task_key=task_key,
            trace_id=effective_trace_id,
            force_skill_names=skill_names,
            force_mcp_server_ids=mcp_server_ids,
            bot_key=executor_id,
        )
    except Exception as e:
        error_msg = f"Agent 执行任务失败：{str(e)}"
        insert_project_log(
            database_path,
            trace_id=trace_id,
            level="ERROR",
            category="task",
            source="bot_task",
            message=f"bot_task 失败：{task_name} - Agent 异常",
            detail=error_msg,
        )
        return {
            "ok": False,
            "summary": error_msg,
        }

    normalized_result_text = _normalize_bot_task_result_text(result_text)
    notify_sent = _has_notify_me_delivery(
        database_path,
        trace_id=effective_trace_id,
        bot_key=executor_id,
    )
    if notify_sent:
        delivered_text = _extract_notify_delivery_result_text(
            database_path,
            trace_id=effective_trace_id,
            bot_key=executor_id,
        )
        delivered_text = _normalize_bot_task_result_text(delivered_text)
        if delivered_text and (not normalized_result_text or _is_notify_skip_payload(normalized_result_text)):
            normalized_result_text = delivered_text

    # 检查是否返回了 fallback_text（表示失败）；如果 notify-me 已送达，则以送达内容为准。
    is_fallback = result_text == settings.agent.fallback_text
    if is_fallback and not normalized_result_text:
        error_msg = "Agent 执行任务失败，返回了降级回复"
        if not notify_sent:
            notify_ok, notify_detail = _send_bot_task_result_notification(
                database_path,
                bot_key=executor_id,
                task_key=task_key,
                task_name=task_name,
                result_text=error_msg,
                trace_id=effective_trace_id,
            )
            if notify_ok:
                notify_sent = True
            else:
                error_msg = f"{error_msg}；通知发送失败：{notify_detail}"
        insert_project_log(
            database_path,
            trace_id=trace_id,
            level="ERROR",
            category="task",
            source="bot_task",
            message=f"bot_task 失败：{task_name} - 返回降级回复",
            detail=f"result={result_text}",
        )
        return {
            "ok": False,
            "summary": error_msg,
        }

    if not normalized_result_text:
        error_msg = "Agent 执行任务失败，未产出可用结果"
        if not notify_sent:
            notify_ok, notify_detail = _send_bot_task_result_notification(
                database_path,
                bot_key=executor_id,
                task_key=task_key,
                task_name=task_name,
                result_text=error_msg,
                trace_id=effective_trace_id,
            )
            if notify_ok:
                notify_sent = True
            else:
                error_msg = f"{error_msg}；通知发送失败：{notify_detail}"
        insert_project_log(
            database_path,
            trace_id=trace_id,
            level="ERROR",
            category="task",
            source="bot_task",
            message=f"bot_task 失败：{task_name} - 结果为空",
            detail=f"result={result_text}",
        )
        return {
            "ok": False,
            "summary": error_msg,
        }

    if not notify_sent:
        insert_project_log(
            database_path,
            trace_id=effective_trace_id,
            level="WARNING",
            category="task",
            source="bot_task",
            message=f"bot_task 缺少 notify-me：{task_name}",
            detail="notify-me 未实际发送，改由运行时补发结果通知",
        )
        notify_ok, notify_detail = _send_bot_task_result_notification(
            database_path,
            bot_key=executor_id,
            task_key=task_key,
            task_name=task_name,
            result_text=normalized_result_text,
            trace_id=effective_trace_id,
        )
        if not notify_ok:
            insert_project_log(
                database_path,
                trace_id=trace_id,
                level="ERROR",
                category="task",
                source="bot_task",
                message=f"bot_task 失败：{task_name} - 通知发送失败",
                detail=notify_detail,
            )
            return {
                "ok": False,
                "summary": f"任务结果已生成，但通知发送失败：{notify_detail}",
            }

    # 记录 token 使用量
    provider_key, provider_type, model = _resolve_provider_details(settings)
    token_usage = {
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "total_tokens": input_tokens + output_tokens,
    }
    _record_task_token_usage(
        database_path,
        trace_id=effective_trace_id,
        call_type="bot_task",
        token_usage=token_usage,
        provider_key=provider_key,
        provider_type=provider_type,
        model=model,
    )

    insert_project_log(
        database_path,
        trace_id=trace_id,
        level="INFO",
        category="task",
        source="bot_task",
        message=f"bot_task 完成：{task_name}",
        detail=(
            f"stage=完成\n"
            f"result={normalized_result_text[:2000]}\n"
            f"input_tokens={input_tokens}\n"
            f"output_tokens={output_tokens}"
        ),
    )

    return {
        "ok": True,
        "summary": "任务执行成功，结果已通过 notify-me 通知",
        "result": normalized_result_text,
        "token_usage": token_usage,
    }
