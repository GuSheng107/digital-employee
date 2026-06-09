from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, Path as FastAPIPath, Query, Request
from fastapi.responses import FileResponse, StreamingResponse
from pathlib import Path

from agent_runtime import AgentService
from app.api_response import ApiError
from app.context_store import get_context_compression_disabled_reason, resolve_context_sender
from app.chat_store import (
    clear_conversation_send_error,
    delete_conversations,
    get_conversation,
    get_latest_messages_for_chats,
    get_last_unreplied_user_message,
    list_conversations,
    mark_conversation_read,
    read_chat_messages,
    set_conversation_archived,
    set_conversation_unarchived,
    set_conversation_pinned,
    set_conversation_reply_mode,
    update_conversation_display_name,
)
from app.db.ai_work_store import (
    clear_ai_work_item,
    cancel_ai_work_item,
    create_ai_work_item,
    get_ai_work_status,
    is_ai_work_cancel_requested,
    update_ai_work_item,
)
from app.db.bot_store import get_bot_config, get_bot_runtime_settings
from app.db.log_store import insert_project_log
from app.db.settings_store import load_settings_from_database
from app.db.user_store import update_user_display_name
from app.exceptions import NotFoundError, ValidationError
from app.manual_reply_attachments import persist_attachment, resolve_attachment_path
from app.manual_reply_queue import enqueue_manual_reply, get_manual_reply
from app.routers._deps import get_database_path, get_project_root
from app.routers._utils import _group_chat_messages
from app.routers.auth import require_admin, require_non_guest
from app.db.token_usage_store import get_latest_token_usage
from app.db.slot_store import is_chat_locked, wait_for_chat_compress_unlock

router = APIRouter(prefix="/api", tags=["chats"])


def _ensure_bot_ai_available(*, database_path: Path, bot_key: str) -> None:
    bot = get_bot_config(database_path, bot_key)
    if not bot:
        raise NotFoundError("Bot 未找到")
    if not str(bot.get("agent_provider") or "").strip():
        raise ValidationError("该 Bot 未挂载 Agent，只能手动回复。")
    settings = get_bot_runtime_settings(database_path, bot_key=bot_key)
    provider_key = str(settings.agent.provider or "").strip()
    if not provider_key:
        raise ValidationError("当前 Bot 未绑定可用的 Agent。")
    if not settings.agent.providers.get(provider_key):
        raise ValidationError("当前 Bot 挂载的 Agent 配置不存在。")
    if not settings.agent.enabled:
        raise ValidationError("当前 Bot 的 Agent 能力不可用，请检查绑定状态和 Agent 配置。")


def _ensure_chat_ai_enabled(*, database_path: Path, chat_id: str) -> None:
    conversation = get_conversation(chat_id=chat_id, database_path=database_path)
    if not conversation:
        raise NotFoundError("会话未找到")
    if str(conversation.get("last_send_error") or "").strip():
        raise ValidationError("当前会话最近发送失败，已自动切换到手动模式，请先手动发送成功后再启用 AI。")


def _ensure_chat_context_compression_allowed(*, database_path: Path, chat_id: str) -> None:
    skip_reason, message = get_context_compression_disabled_reason(
        database_path=database_path,
        chat_id=chat_id,
    )
    if not skip_reason:
        return
    if skip_reason == "not_found":
        raise NotFoundError(message)
    raise ValidationError(f"{message}。")


def _format_bytes(value: int) -> str:
    if value >= 1024 * 1024:
        amount = value / (1024 * 1024)
        return f"{amount:.0f}MB" if amount.is_integer() else f"{amount:.1f}MB"
    if value >= 1024:
        amount = value / 1024
        return f"{amount:.0f}KB" if amount.is_integer() else f"{amount:.1f}KB"
    return f"{value}B"


def _attachment_limit_bytes(settings: Any, kind: str) -> int:
    normalized = kind if kind in {"image", "video", "audio"} else "file"
    attr = {
        "image": "max_image_bytes",
        "video": "max_video_bytes",
        "audio": "max_audio_bytes",
        "file": "max_file_bytes",
    }[normalized]
    return int(getattr(settings.agent, attr, 0) or 0)


def _validate_web_upload_attachment_limits(
    attachments: list[dict[str, Any]],
    *,
    settings: Any,
) -> None:
    labels = {"image": "图片", "video": "视频", "audio": "音频", "file": "文件"}
    for attachment in attachments:
        kind = str(attachment.get("kind") or "file").strip().lower()
        normalized = kind if kind in {"image", "video", "audio"} else "file"
        size = int(attachment.get("size") or 0)
        limit = _attachment_limit_bytes(settings, normalized)
        if limit > 0 and size > limit:
            filename = str(attachment.get("filename") or "附件").strip() or "附件"
            label = labels.get(normalized, "文件")
            raise ValidationError(
                f"{label}「{filename}」超过上传大小限制：{_format_bytes(size)} > {_format_bytes(limit)}"
            )


def _operator_log_detail(request: Request) -> str:
    user = getattr(request.state, "auth_user", None)
    if not isinstance(user, dict):
        return "\n".join([
            "operator_username=<empty>",
            "operator_display_name=<empty>",
            "operator_role=<empty>",
        ])
    username = str(user.get("username") or "").strip() or "<empty>"
    display_name = str(user.get("display_name") or "").strip() or "<empty>"
    role = str(user.get("role") or "").strip() or "<empty>"
    return "\n".join([
        f"operator_username={username}",
        f"operator_display_name={display_name}",
        f"operator_role={role}",
    ])


@router.get("/chats", summary="获取会话列表", description="获取指定 Bot 的会话列表，支持分页和关键字搜索")
def get_chats(
    bot_key: str = Query("", description="Bot Key"),
    keyword: str = Query("", description="搜索关键字"),
    page: int = Query(1, description="页码"),
    page_size: int = Query(50, description="每页数量"),
    limit: int = Query(500, description="加载的历史消息数量限制"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    if not bot_key:
        return {"chats": [], "page": {"items": [], "page": 1, "page_size": page_size, "total": 0}}
    conversations = list_conversations(
        database_path=database_path,
        bot_key=bot_key,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    conversation_items = conversations["items"]
    conversation_chat_ids = [
        str(item.get("chat_id") or "").strip()
        for item in conversation_items
        if str(item.get("chat_id") or "").strip()
    ]
    messages = read_chat_messages(
        limit=max(limit, len(conversation_chat_ids) * 50),
        database_path=database_path,
        bot_key=bot_key,
        chat_ids=conversation_chat_ids,
    )
    chats = _group_chat_messages(
        messages,
        conversations=conversation_items,
        database_path=database_path,
    )
    latest_messages = get_latest_messages_for_chats(
        chat_ids=conversation_chat_ids,
        database_path=database_path,
    )
    for chat in chats:
        if str(chat.get("last_message") or "").strip():
            continue
        latest = latest_messages.get(str(chat.get("chat_id") or "").strip())
        if latest is None:
            continue
        chat["last_message"] = str(latest.get("content") or "")
        chat["last_at"] = str(latest.get("created_at") or chat.get("last_at") or "")
        chat["messages"] = []
    for chat in chats:
        chat["messages"] = []
    return {"chats": chats, "page": conversations}


@router.get("/chats/{chat_id}", summary="获取会话详情", description="获取指定会话的详细消息内容")
def get_chat_detail(
    chat_id: str = FastAPIPath(..., description="会话 ID"),
    limit: int = Query(200, description="加载的历史消息数量"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    conversation = get_conversation(chat_id=chat_id, database_path=database_path)
    if not conversation:
        raise NotFoundError("会话未找到")
    messages = read_chat_messages(
        limit=max(1, min(limit, 1000)),
        database_path=database_path,
        chat_ids=[chat_id],
    )
    chats = _group_chat_messages(
        messages,
        conversations=[conversation],
        database_path=database_path,
    )
    if chats:
        return {"chat": chats[0]}
    latest = get_latest_messages_for_chats(chat_ids=[chat_id], database_path=database_path).get(chat_id)
    fallback = dict(conversation)
    fallback["messages"] = []
    fallback["last_message"] = str((latest or {}).get("content") or "")
    fallback["last_at"] = str((latest or {}).get("created_at") or conversation.get("last_message_at") or "")
    return {"chat": fallback}


@router.delete("/chats", summary="批量删除会话", description="批量删除指定的会话")
def batch_delete_chats(
    request: Request,
    payload: dict[str, Any] = Body(..., description="包含 chat_ids 字段的对象：chat_ids（字符串数组，要删除的会话 ID 列表）"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_admin(request)
    chat_ids = payload.get("chat_ids", [])
    if not isinstance(chat_ids, list):
        raise ValidationError("chat_ids 必须是列表")
    deleted = delete_conversations(
        chat_ids=[str(item) for item in chat_ids],
        database_path=database_path,
    )
    return {"ok": True, "deleted": deleted}


@router.post("/chats/{chat_id}/read", summary="标记会话为已读", description="标记指定会话为已读状态")
def read_chat(
    request: Request,
    chat_id: str = FastAPIPath(..., description="会话 ID"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    mark_conversation_read(chat_id=chat_id, database_path=database_path)
    return {"ok": True}


@router.post("/chats/{chat_id}/reply-mode", summary="设置会话回复模式", description="设置会话的回复模式为手动或 AI，切换 AI 模式需要 Bot 配置正确")
def set_chat_reply_mode(
    request: Request,
    chat_id: str = FastAPIPath(..., description="会话 ID"),
    payload: dict[str, Any] = Body(..., description="包含 reply_mode 和 bot_key 字段的对象：reply_mode（'manual'或'ai'）、bot_key（切换到 AI 模式时必需）"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    reply_mode = str(payload.get("reply_mode", "")).strip()
    if reply_mode not in ("manual", "ai"):
        raise ValidationError("reply_mode 必须是 'manual' 或 'ai'")
    if reply_mode == "ai":
        bot_key = str(payload.get("bot_key") or "").strip()
        if not bot_key:
            raise ValidationError("切换 AI 回复模式时缺少 bot_key。")
        _ensure_chat_ai_enabled(database_path=database_path, chat_id=chat_id)
        _ensure_bot_ai_available(database_path=database_path, bot_key=bot_key)
    return {
        "ok": True,
        "conversation": set_conversation_reply_mode(
            chat_id=chat_id,
            reply_mode=reply_mode,
            database_path=database_path,
        ),
    }


@router.post("/chats/{chat_id}/archive", summary="归档会话", description="归档指定会话")
def archive_chat(
    request: Request,
    chat_id: str = FastAPIPath(..., description="会话 ID"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    return {
        "ok": True,
        "conversation": set_conversation_archived(
            chat_id=chat_id,
            database_path=database_path,
        ),
    }


@router.post("/chats/{chat_id}/unarchive", summary="取消归档会话", description="将已归档的会话恢复为活跃状态")
def unarchive_chat(
    request: Request,
    chat_id: str = FastAPIPath(..., description="会话 ID"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    return {
        "ok": True,
        "conversation": set_conversation_unarchived(
            chat_id=chat_id,
            database_path=database_path,
        ),
    }


@router.post("/chats/{chat_id}/clear-send-error", summary="清除会话发送错误", description="清除指定会话的发送错误标记，允许重新启用 AI 模式")
def clear_send_error(
    request: Request,
    chat_id: str = FastAPIPath(..., description="会话 ID"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    clear_conversation_send_error(chat_id=chat_id, database_path=database_path)
    return {"ok": True}


@router.post("/chats/{chat_id}/pin", summary="置顶/取消置顶会话", description="置顶或取消置顶指定会话")
def pin_chat(
    request: Request,
    chat_id: str = FastAPIPath(..., description="会话 ID"),
    payload: dict[str, Any] = Body(..., description="包含 pinned 字段的对象：pinned（布尔，true=置顶，false=取消置顶）"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    return {
        "ok": True,
        "conversation": set_conversation_pinned(
            chat_id=chat_id,
            pinned=bool(payload.get("pinned", True)),
            database_path=database_path,
        ),
    }


@router.post("/chats/{chat_id}/display-name", summary="设置会话显示名称", description="设置指定会话的显示名称")
def set_chat_display_name(
    request: Request,
    chat_id: str = FastAPIPath(..., description="会话 ID"),
    payload: dict[str, Any] = Body(..., description="包含 display_name 字段的对象：display_name（字符串，会话显示名称）"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    display_name = str(payload.get("display_name", "")).strip()
    return {
        "ok": True,
        "conversation": update_conversation_display_name(
            chat_id=chat_id,
            display_name=display_name,
            database_path=database_path,
        ),
    }


@router.post("/users/{user_id}/display-name", summary="设置用户显示名称", description="设置指定用户的显示名称")
def set_user_display_name(
    request: Request,
    user_id: str = FastAPIPath(..., description="用户 ID"),
    payload: dict[str, Any] = Body(..., description="包含 display_name 字段的对象：display_name（字符串，用户显示名称）"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    display_name = str(payload.get("display_name", "")).strip()
    profile = update_user_display_name(
        database_path,
        user_id=user_id,
        display_name=display_name,
    )
    return {"ok": True, "user": profile or {"user_id": user_id, "display_name": ""}}


@router.post("/chats/{chat_id}/context/compress", summary="压缩会话上下文", description="压缩指定会话的历史上下文，生成摘要")
async def compress_chat_context(
    request: Request,
    chat_id: str = FastAPIPath(..., description="会话 ID"),
    database_path: Path = Depends(get_database_path),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    require_non_guest(request)
    from app.context_store import get_context_usage
    from uuid import uuid4

    _ensure_chat_context_compression_allowed(database_path=database_path, chat_id=chat_id)

    settings = load_settings_from_database(database_path)
    trace_id = str(uuid4())
    agent_service = AgentService(settings, project_root=project_root)
    agent_service.database_path = database_path
    context_sender = resolve_context_sender(database_path=database_path, chat_id=chat_id)
    compress_result = await agent_service.compress_context_if_needed(
        chat_id,
        sender_id=context_sender["sender_id"],
        trace_id=trace_id,
    )
    return {
        "ok": True,
        "trace_id": trace_id,
        "summary": compress_result.get("summary", ""),
        "triggered": compress_result.get("triggered", False),
        "skipped": compress_result.get("skipped", False),
        "compressed": compress_result.get("compressed", False),
        "error": compress_result.get("error", ""),
        "usage": get_context_usage(
            database_path=database_path,
            chat_id=chat_id,
            sender_id=context_sender["sender_id"],
        ),
    }


@router.post("/chats/{chat_id}/ai-draft", summary="生成 AI 回复草稿", description="为指定会话生成 AI 回复草稿，支持流式输出")
async def generate_ai_draft(
    request: Request,
    chat_id: str = FastAPIPath(..., description="会话 ID"),
    payload: dict[str, Any] = Body(..., description="包含 bot_key 和 chat_name 字段的对象：bot_key（字符串，必需）、chat_name（字符串，可选）"),
    database_path: Path = Depends(get_database_path),
    project_root: Path = Depends(get_project_root),
) -> StreamingResponse:
    require_non_guest(request)
    bot_key = str(payload.get("bot_key") or "").strip()
    if not bot_key:
        raise ValidationError("生成 AI 回复时缺少 bot_key。")
    _ensure_chat_ai_enabled(database_path=database_path, chat_id=chat_id)
    _ensure_bot_ai_available(database_path=database_path, bot_key=bot_key)
    trace_id = str(uuid4())
    last_user_msg = get_last_unreplied_user_message(chat_id=chat_id, database_path=database_path)
    user_text = str(last_user_msg.get("content") or "").strip() if last_user_msg else ""
    if not user_text:
        raise ValidationError("当前会话没有未回复的用户消息，无法生成 AI 草稿。")
    settings = get_bot_runtime_settings(database_path, bot_key=bot_key)
    chat_name = str(payload.get("chat_name") or chat_id)
    create_ai_work_item(
        database_path,
        trace_id=trace_id,
        chat_id=chat_id,
        chat_name=chat_name,
        question=user_text,
        stage="按钮触发生成回复",
    )
    insert_project_log(
        database_path,
        trace_id=trace_id,
        level="INFO",
        category="ai",
        source="ai_task",
        message="AI task started",
        detail=(
            f"{_operator_log_detail(request)}\n"
            f"bot_key={bot_key}\n"
            f"chat_id={chat_id}\n"
            f"chat_name={chat_name}\n"
            f"stage=按钮触发生成回复\n"
            f"question={user_text[:500]}"
        ),
    )

    async def _draft_detail(
        *,
        stage: str = "",
        question: str = "",
        answer: str = "",
        error: str = "",
    ) -> str:
        parts = [
            _operator_log_detail(request),
            f"bot_key={bot_key}",
            f"chat_id={chat_id}",
            f"chat_name={chat_name}",
        ]
        if stage:
            parts.append(f"stage={stage}")
        if question:
            parts.append(f"question={str(question)[:500].replace(chr(10), ' ')}")
        if answer:
            parts.append(f"answer={str(answer)[:1200].replace(chr(10), ' ')}")
        if error:
            parts.append(f"error={str(error)[:1200].replace(chr(10), ' ')}")
        return "\n".join(parts)

    async def event_generator():
        collected_parts: list[str] = []
        agent_service = AgentService(settings, project_root=project_root)
        yield f"data: {json.dumps({'type': 'start', 'trace_id': trace_id}, ensure_ascii=False)}\n\n"
        try:
            if is_chat_locked(database_path, chat_id=chat_id):
                yield f"data: {json.dumps({'type': 'compressing', 'message': '当前会话正在压缩上下文，压缩完成后自动生成 AI 草稿'}, ensure_ascii=False)}\n\n"
                update_ai_work_item(
                    database_path,
                    trace_id=trace_id,
                    status="running",
                    stage="等待上下文压缩",
                )
                unlocked = await wait_for_chat_compress_unlock(database_path, chat_id=chat_id)
                if not unlocked:
                    update_ai_work_item(
                        database_path,
                        trace_id=trace_id,
                        status="failed",
                        error="上下文压缩等待超时",
                    )
                    yield f"data: {json.dumps({'type': 'error', 'error': '上下文压缩等待超时，请稍后重试'}, ensure_ascii=False)}\n\n"
                    return

            update_ai_work_item(
                database_path,
                trace_id=trace_id,
                status="running",
                stage="构建上下文并调用 Agent（流式）",
            )
            last_update = 0.0
            last_cancel_check = 0.0
            async for token in agent_service.stream_answer(
                user_text,
                chat_id=chat_id,
                trace_id=trace_id,
                call_type="draft",
                bot_key=bot_key,
                sender_id=str(last_user_msg.get("sender_id") or ""),
                sender_name=str(last_user_msg.get("sender_name") or ""),
                cancel_check=lambda: is_ai_work_cancel_requested(database_path, trace_id),
            ):
                now = time.time()
                if now - last_cancel_check > 0.3:
                    last_cancel_check = now
                    if is_ai_work_cancel_requested(database_path, trace_id):
                        break
                collected_parts.append(token)
                yield f"data: {json.dumps({'type': 'token', 'content': token}, ensure_ascii=False)}\n\n"
                if now - last_update > 0.5:
                    if not is_ai_work_cancel_requested(database_path, trace_id):
                        update_ai_work_item(
                            database_path,
                            trace_id=trace_id,
                            status="running",
                            answer="".join(collected_parts),
                            stage="Agent 推理中",
                        )
                    last_update = now

            if is_ai_work_cancel_requested(database_path, trace_id):
                update_ai_work_item(
                    database_path,
                    trace_id=trace_id,
                    status="cancelled",
                    answer="",
                    stage="已截断",
                )
                insert_project_log(
                    database_path,
                    trace_id=trace_id,
                    level="INFO",
                    category="ai",
                    source="ai_task",
                    message="AI task cancelled",
                    detail=await _draft_detail(stage="已截断", question=user_text),
                )
                yield f"data: {json.dumps({'type': 'cancelled', 'trace_id': trace_id}, ensure_ascii=False)}\n\n"
                return

            full_answer = "".join(collected_parts)
            update_ai_work_item(
                database_path,
                trace_id=trace_id,
                status="completed",
                answer=full_answer,
                stage="完成",
            )
            insert_project_log(
                database_path,
                trace_id=trace_id,
                level="INFO",
                category="ai",
                source="ai_task",
                message="AI task completed",
                detail=await _draft_detail(stage="完成", question=user_text, answer=full_answer),
            )
            _log_token_usage_if_present(
                database_path=database_path,
                trace_id=trace_id,
                category="ai",
                source="token_usage",
                message="AI task token usage",
            )
            yield f"data: {json.dumps({'type': 'done', 'trace_id': trace_id}, ensure_ascii=False)}\n\n"
        except Exception as exc:
            partial_answer = "".join(collected_parts)
            update_ai_work_item(
                database_path,
                trace_id=trace_id,
                status="failed",
                answer=partial_answer,
                error=str(exc),
                stage="异常截断",
            )
            insert_project_log(
                database_path,
                trace_id=trace_id,
                level="ERROR",
                category="ai",
                source="ai_task",
                message="AI task failed",
                detail=await _draft_detail(
                    stage="异常截断",
                    question=user_text,
                    answer=partial_answer,
                    error=str(exc),
                ),
            )
            yield f"data: {json.dumps({'type': 'error', 'error': str(exc)[:500], 'trace_id': trace_id}, ensure_ascii=False)}\n\n"

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.post("/chats/{chat_id}/reply", summary="发送手动回复", description="向指定会话发送手动回复，支持文本和附件")
async def manual_reply(
    chat_id: str = FastAPIPath(..., description="会话 ID"),
    request: Request = Request,
    database_path: Path = Depends(get_database_path),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    require_non_guest(request)
    payload, attachments = await _parse_manual_reply_request(request, project_root=project_root)
    content = str(payload.get("content", "")).strip()
    if not content and not attachments:
        raise ValidationError("回复内容和附件不能同时为空。")

    if attachments:
        settings = load_settings_from_database(database_path)
        _validate_web_upload_attachment_limits(attachments, settings=settings)
    
    # 持久化附件，这样在记录消息时就有URL可以显示了
    processed_attachments = []
    for attachment in attachments:
        if "_content_bytes" in attachment:
            persisted = persist_attachment(
                project_root,
                filename=attachment["filename"],
                content=attachment["_content_bytes"],
                mime_type=attachment["mime_type"],
            )
            processed_attachments.append({
                "filename": persisted["filename"],
                "mime_type": persisted["mime_type"],
                "size": persisted["size"],
                "kind": attachment.get("kind") or persisted["kind"],
                "storage_name": persisted["storage_name"],
                "storage_path": persisted["storage_path"],
                "url": persisted["url"],
            })
        else:
            processed_attachments.append(attachment)
    
    metadata: dict[str, Any] = {"attachments": processed_attachments}
    target_user_msg = get_last_unreplied_user_message(chat_id=chat_id, database_path=database_path)
    target_sender_id = str(target_user_msg.get("sender_id") or "").strip()
    target_sender_name = str(target_user_msg.get("sender_name") or "").strip()
    if not target_sender_id:
        context_sender = resolve_context_sender(database_path=database_path, chat_id=chat_id)
        target_sender_id = context_sender["sender_id"]
        target_sender_name = context_sender["sender_name"]
    if target_sender_id:
        metadata["target_sender_id"] = target_sender_id
    if target_sender_name:
        metadata["target_sender_name"] = target_sender_name
    source_trace_id = str(payload.get("source_trace_id") or "").strip()
    if source_trace_id:
        metadata["source_trace_id"] = source_trace_id
    command = enqueue_manual_reply(
        chat_id=str(payload.get("external_chat_id") or chat_id),
        chat_name=str(payload.get("chat_name") or chat_id),
        content=content,
        database_path=database_path,
        bot_key=str(payload.get("bot_key") or ""),
        conversation_chat_id=chat_id,
        external_chat_id=str(payload.get("external_chat_id") or chat_id),
        metadata=metadata,
    )
    return {"ok": True, "trace_id": command.id, "command": asdict(command)}


@router.get("/manual-replies/{command_id}", summary="获取手动回复状态", description="获取指定手动回复命令的发送状态")
def get_manual_reply_status(
    command_id: str = FastAPIPath(..., description="命令 ID"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    command = get_manual_reply(command_id, database_path=database_path)
    if not command:
        raise NotFoundError("手动回复命令未找到")
    # 正常返回状态，即使是失败状态，让前端处理
    return {"ok": True, "trace_id": command_id, "command": command}


@router.post("/ai/status/{trace_id}/cancel", summary="取消 AI 任务", description="取消指定的 AI 任务")
def cancel_ai(
    request: Request,
    trace_id: str = FastAPIPath(..., description="任务 ID"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    return {"ok": cancel_ai_work_item(database_path, trace_id)}


@router.delete("/ai/status/{trace_id}", summary="清除 AI 任务", description="清除指定的 AI 任务记录")
def clear_ai(
    request: Request,
    trace_id: str = FastAPIPath(..., description="任务 ID"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_admin(request)
    return {"ok": clear_ai_work_item(database_path, trace_id)}


@router.get("/ai/status", summary="获取 AI 任务状态", description="获取所有 AI 任务的当前状态")
def get_ai_status(
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    return get_ai_work_status(database_path)


_SSE_MAX_ITERATIONS = 600
_SSE_IDLE_INTERVAL = 2.0
_SSE_ACTIVE_INTERVAL = 0.5


@router.get("/ai/status/stream", summary="流式获取 AI 任务状态", description="流式推送 AI 任务的状态更新")
async def stream_ai_status(
    request: Request,
    database_path: Path = Depends(get_database_path),
) -> StreamingResponse:
    async def event_generator():
        iterations = 0
        previous_data: dict[str, Any] | None = None
        while not await request.is_disconnected():
            iterations += 1
            if iterations > _SSE_MAX_ITERATIONS:
                yield f"data: {json.dumps({'type': 'heartbeat'}, ensure_ascii=False)}\n\n"
                break
            data = get_ai_work_status(database_path)
            current_json = json.dumps(data, ensure_ascii=False)
            if current_json != previous_data:
                yield f"data: {current_json}\n\n"
                previous_data = current_json
                await asyncio.sleep(_SSE_ACTIVE_INTERVAL)
            else:
                await asyncio.sleep(_SSE_IDLE_INTERVAL)

    return StreamingResponse(
        event_generator(),
        media_type="text/event-stream",
        headers={
            "Cache-Control": "no-cache",
            "Connection": "keep-alive",
            "X-Accel-Buffering": "no",
        },
    )


@router.get("/manual-reply-attachments/{storage_name}", summary="获取手动回复附件", description="下载指定的手动回复附件")
def get_manual_reply_attachment(
    storage_name: str = FastAPIPath(..., description="附件存储名称"),
    project_root: Path = Depends(get_project_root),
) -> FileResponse:
    path = resolve_attachment_path(project_root, storage_name)
    if not path.exists() or not path.is_file():
        raise NotFoundError("附件不存在")
    media_type = "application/octet-stream"
    if path.suffix:
        import mimetypes

        media_type = mimetypes.guess_type(path.name)[0] or media_type
    return FileResponse(path=str(path), media_type=media_type)


def _infer_kind_from_mime(mime_type: str, filename: str = "") -> str:
    normalized = mime_type.strip().lower().split(";")[0].strip()
    if not normalized or normalized == "application/octet-stream":
        if filename:
            import mimetypes

            normalized = str(mimetypes.guess_type(filename)[0] or "").strip().lower()
    if normalized.startswith("image/"):
        return "image"
    if normalized.startswith("video/"):
        return "video"
    if normalized.startswith("audio/"):
        return "audio"
    return "file"


async def _parse_manual_reply_request(
    request: Request,
    *,
    project_root: Path,
) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    content_type = str(request.headers.get("content-type") or "").lower()
    if "multipart/form-data" not in content_type:
        payload = await request.json()
        if not isinstance(payload, dict):
            raise ValidationError("请求体格式无效")
        return payload, []

    form = await request.form()
    payload = {
        "content": str(form.get("content") or "").strip(),
        "bot_key": str(form.get("bot_key") or "").strip(),
        "external_chat_id": str(form.get("external_chat_id") or "").strip(),
        "chat_name": str(form.get("chat_name") or "").strip(),
        "source_trace_id": str(form.get("source_trace_id") or "").strip(),
    }
    attachments: list[dict[str, Any]] = []
    for item in form.getlist("files"):
        filename = str(getattr(item, "filename", "") or "").strip()
        if not filename:
            continue
        file_content = await item.read()
        mime_type = str(getattr(item, "content_type", "") or "").strip()
        kind = _infer_kind_from_mime(mime_type, filename)
        attachments.append({
            "filename": filename,
            "mime_type": mime_type,
            "size": len(file_content),
            "kind": kind,
            "_content_bytes": file_content,
        })
    return payload, attachments


def _log_token_usage_if_present(
    *,
    database_path: Path,
    trace_id: str,
    category: str,
    source: str,
    message: str,
) -> None:
    usage = get_latest_token_usage(database_path, trace_id=trace_id)
    if not usage:
        return
    insert_project_log(
        database_path,
        trace_id=trace_id,
        level="INFO",
        category=category,
        source=source,
        message=message,
        detail=(
            f"call_type={usage.get('call_type', '')}\n"
            f"provider_key={usage.get('provider_key', '')}\n"
            f"provider_type={usage.get('provider_type', '')}\n"
            f"model={usage.get('model', '')}\n"
            f"input_tokens={usage.get('input_tokens', 0)}\n"
            f"output_tokens={usage.get('output_tokens', 0)}\n"
            f"total_tokens={usage.get('total_tokens', 0)}"
        ),
    )
