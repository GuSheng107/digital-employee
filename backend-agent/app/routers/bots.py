from __future__ import annotations

from dataclasses import asdict
import time
from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, Path as FastAPIPath, Query, Request
from pathlib import Path

from app.bot_process_manager import BotProcessManager
from app.chat_store import (
    get_bot_unread_total,
    list_active_bot_conversations,
    mark_all_bot_conversations_read,
)
from app.config_loader import validate_settings
from app.db.bot_store import (
    batch_delete_bots,
    get_bot_config,
    get_bot_runtime_settings,
    list_bot_configs,
    list_bot_configs_paginated,
    list_bots_by_keys,
    mark_bot_rebinding,
    restore_bots,
    toggle_bot_active,
    unbind_bot,
    upsert_bot_config,
)
from app.db.mapping_store import (
    get_bot_mcp_mappings,
    get_bot_mapping_counts,
    get_bot_skill_mappings,
    save_bot_mcp_mappings,
    save_bot_skill_mappings,
)
from app.db.mcp_store import list_mcp_servers
from app.db.skill_store import (
    get_enabled_skill_names,
    get_skill_display_names,
    sync_skill_catalog,
)
from app.db.core import initialize_database
from app.exceptions import AppError, ConfigError, ConflictError, NotFoundError, ValidationError
from app.manual_reply_queue import enqueue_manual_reply, get_manual_reply
from app.routers._deps import get_database_path, get_manager, get_project_root
from app.routers._utils import _bot_api_view
from app.routers.auth import require_admin, require_non_guest
from app.skills_store import scan_skills

router = APIRouter(prefix="/api/bots", tags=["bots"])


def _should_skip_broadcast_conversation(
    conversation: dict[str, Any],
    *,
    bound_chat_id: str = "",
) -> bool:
    chat_id = str(conversation.get("chat_id") or "").strip()
    external_chat_id = str(conversation.get("external_chat_id") or "").strip()
    conversation_kind = str(conversation.get("conversation_kind") or "").strip()

    if chat_id.startswith("precheck:") or external_chat_id.startswith("precheck:"):
        return True
    if conversation_kind == "me" and bound_chat_id:
        return external_chat_id != bound_chat_id
    return False


def _ensure_bot_mapping_editable(
    *,
    bot: dict[str, Any] | None,
    manager: BotProcessManager,
) -> None:
    if bot is None:
        raise NotFoundError("Bot 未找到")
    bot_key = str(bot.get("bot_key") or "").strip()
    if bot_key and manager.status(bot_key).get("running"):
        raise ConflictError("Bot 运行中不允许修改 MCP/Skill 映射")


def _enqueue_bot_broadcast(
    *,
    bot_key: str,
    content: str,
    database_path: Path,
    bound_chat_id: str = "",
    skip_record: bool = False,
) -> list[str]:
    text = str(content or "").strip()
    if not text:
        return []

    commands: list[str] = []
    for conversation in list_active_bot_conversations(bot_key=bot_key, database_path=database_path):
        if _should_skip_broadcast_conversation(conversation, bound_chat_id=bound_chat_id):
            continue
        external_chat_id = str(conversation.get("external_chat_id") or "").strip()
        conversation_chat_id = str(conversation.get("chat_id") or "").strip()
        if not external_chat_id or not conversation_chat_id:
            continue
        command = enqueue_manual_reply(
            chat_id=external_chat_id,
            chat_name=str(conversation.get("display_name") or conversation.get("chat_name") or external_chat_id),
            content=text,
            database_path=database_path,
            bot_key=bot_key,
            conversation_chat_id=conversation_chat_id,
            external_chat_id=external_chat_id,
            skip_record=skip_record,
        )
        commands.append(command.id)
    return commands


def _wait_manual_replies_sent(
    *,
    command_ids: list[str],
    database_path: Path,
    timeout_seconds: float = 30.0,
) -> dict[str, int]:
    if not command_ids:
        return {"sent": 0, "failed": 0, "pending": 0}

    deadline = time.time() + timeout_seconds
    pending_ids = set(command_ids)
    sent = 0
    failed = 0
    while pending_ids and time.time() < deadline:
        completed_now: list[str] = []
        for command_id in list(pending_ids):
            command = get_manual_reply(command_id, database_path=database_path)
            status = str(command.get("status") or "")
            if status == "sent":
                sent += 1
                completed_now.append(command_id)
            elif status == "failed":
                failed += 1
                completed_now.append(command_id)
        for command_id in completed_now:
            pending_ids.discard(command_id)
        if pending_ids:
            time.sleep(0.2)
    return {"sent": sent, "failed": failed, "pending": len(pending_ids)}


def _send_shutdown_text_if_needed(
    *,
    bot_key: str,
    database_path: Path,
) -> None:
    from app.utils import utc_now
    from datetime import datetime

    bot = get_bot_config(database_path, bot_key)
    if not bot:
        return
    shutdown_text = str(bot.get("shutdown_text") or "").strip()
    if not shutdown_text or str(bot.get("bind_status")) != "bound":
        return

    is_just_bound = False
    bot_updated_at = str(bot.get("updated_at") or "")
    if bot_updated_at:
        try:
            updated_time = datetime.fromisoformat(bot_updated_at)
            now = datetime.fromisoformat(utc_now())
            delta = now - updated_time
            if delta.total_seconds() < 300:
                is_just_bound = True
        except (ValueError, TypeError):
            pass
    
    if is_just_bound:
        return
    
    command_ids = _enqueue_bot_broadcast(
        bot_key=bot_key,
        content=shutdown_text,
        database_path=database_path,
        bound_chat_id=str(bot.get("bound_chat_id") or "").strip(),
        skip_record=True,
    )
    if command_ids:
        _wait_manual_replies_sent(
            command_ids=command_ids,
            database_path=database_path,
            timeout_seconds=30.0,
        )


@router.get("", summary="获取 Bot 列表", description="获取所有 Bot 配置列表，支持分页和关键字搜索")
def get_bots(
    bot_key: str | None = Query(None, description="Bot Key，指定时获取单个 Bot 详情"),
    page: int = Query(1, description="页码"),
    page_size: int = Query(10, description="每页数量"),
    keyword: str = Query("", description="搜索关键字"),
    include_deleted: bool = Query(False, description="是否包含已删除的 Bot"),
    database_path: Path = Depends(get_database_path),
    manager: BotProcessManager = Depends(get_manager),
) -> dict[str, Any]:
    if bot_key:
        bot = get_bot_config(database_path, bot_key)
        if bot is None:
            raise NotFoundError("Bot 未找到")
        mapping_counts = get_bot_mapping_counts(database_path, [bot_key])
        unread_totals = {bot_key: get_bot_unread_total(bot_key=bot_key, database_path=database_path)}
        return {"bot": _bot_api_view(bot, mapping_counts=mapping_counts, unread_totals=unread_totals), "status": manager.status(bot_key)}
    else:
        result = list_bot_configs_paginated(database_path, page, page_size, keyword, include_deleted=include_deleted)
        result["statuses"] = manager.all_statuses(result["bots"])
        bot_keys = [str(bot["bot_key"]) for bot in result["bots"]]
        mapping_counts = get_bot_mapping_counts(database_path, bot_keys) if bot_keys else {}
        unread_totals = {bk: get_bot_unread_total(bot_key=bk, database_path=database_path) for bk in bot_keys}
        result["bots"] = [_bot_api_view(bot, mapping_counts=mapping_counts, unread_totals=unread_totals) for bot in result["bots"]]
        return result


@router.post("", summary="保存 Bot 配置", description="创建或更新 Bot 配置")
def save_bot(
    request: Request,
    payload: dict[str, Any] = Body(..., description="Bot 配置对象，包含 name、bot_key、wecom 配置等"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    try:
        bot = upsert_bot_config(database_path, payload)
        mapping_counts = get_bot_mapping_counts(database_path, [bot["bot_key"]]) if bot else {}
        return {"ok": True, "bot": _bot_api_view(bot, mapping_counts=mapping_counts)}
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    except Exception as exc:
        raise ValidationError("Bot 配置保存失败", detail=str(exc)) from exc


@router.post("/batch-delete", summary="批量删除 Bot", description="批量删除指定的 Bot，已挂载 Agent/Skill/MCP 或正在运行的 Bot 无法删除")
def batch_delete_bots_api(
    request: Request,
    payload: dict[str, Any] = Body(..., description="包含 bot_keys 字段的对象：bot_keys（字符串数组，要删除的 Bot Key 列表）"),
    database_path: Path = Depends(get_database_path),
    manager: BotProcessManager = Depends(get_manager),
) -> dict[str, Any]:
    require_admin(request)
    bot_keys = payload.get("bot_keys", [])
    if not isinstance(bot_keys, list) or len(bot_keys) == 0:
        raise ValidationError("bot_keys 必须是非空列表")
    bots_to_delete = list_bots_by_keys(database_path, [str(item) for item in bot_keys])
    running_enabled = [
        str(bot["name"])
        for bot in bots_to_delete
        if bool(bot["is_active"]) and manager.status(str(bot["bot_key"])).get("running")
    ]
    if running_enabled:
        raise ConflictError(f"无法删除正在运行的已启用 Bot: {', '.join(running_enabled)}")
    for bot in bots_to_delete:
        bot_key = str(bot["bot_key"])
        if str(bot.get("agent_provider") or "").strip():
            raise ConflictError(f"Bot[{bot['name']}] 已挂载 Agent，请先卸载后再删除")
        skill_mappings = get_bot_skill_mappings(database_path, bot_key)
        if skill_mappings:
            raise ConflictError(f"Bot[{bot['name']}] 已挂载 Skill，请先卸载后再删除")
        mcp_mappings = get_bot_mcp_mappings(database_path, bot_key)
        if mcp_mappings:
            raise ConflictError(f"Bot[{bot['name']}] 已挂载 MCP，请先卸载后再删除")
    deleted_count = batch_delete_bots(database_path, bot_keys)
    return {"ok": True, "deleted_count": deleted_count}


@router.post("/restore", summary="恢复已删除的 Bot", description="批量恢复已删除的 Bot")
def restore_deleted_bots_api(
    request: Request,
    payload: dict[str, Any] = Body(..., description="包含 bot_keys 字段的对象：bot_keys（字符串数组，要恢复的 Bot Key 列表）"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    bot_keys = payload.get("bot_keys", [])
    if not isinstance(bot_keys, list) or len(bot_keys) == 0:
        raise ValidationError("bot_keys 必须是非空列表")
    restored_count = restore_bots(database_path, [str(item) for item in bot_keys])
    return {"ok": True, "restored_count": restored_count}


@router.post("/{bot_key}/toggle", summary="启用/停用 Bot", description="启用或停用指定的 Bot，已挂载 Skill/MCP 的 Bot 无法停用")
def toggle_bot_api(
    request: Request,
    bot_key: str = FastAPIPath(..., description="Bot Key"),
    payload: dict[str, Any] = Body(..., description="包含 is_active 字段的对象：is_active（布尔，true=启用，false=停用）"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    is_active = bool(payload.get("is_active", False))
    if not is_active:
        skill_mappings = get_bot_skill_mappings(database_path, bot_key)
        if skill_mappings:
            raise ValidationError(f"Bot 已挂载 Skill，请先卸载后再停用")
        mcp_mappings = get_bot_mcp_mappings(database_path, bot_key)
        if mcp_mappings:
            raise ValidationError(f"Bot 已挂载 MCP，请先卸载后再停用")
    try:
        toggle_bot_active(database_path, bot_key, is_active)
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc
    mapping_counts = get_bot_mapping_counts(database_path, [bot_key])
    return {"ok": True, "bot": _bot_api_view(get_bot_config(database_path, bot_key), mapping_counts=mapping_counts)}


@router.post("/{bot_key}/start", summary="启动 Bot 服务", description="启动指定的 Bot 服务，会发送欢迎消息给活跃会话")
def start_named_bot(
    request: Request,
    bot_key: str = FastAPIPath(..., description="Bot Key"),
    database_path: Path = Depends(get_database_path),
    manager: BotProcessManager = Depends(get_manager),
    payload: dict[str, Any] = Body(default={}, description="可选的启动参数：purpose（字符串，'bind'表示仅绑定）、force（布尔，强制启动无Agent的Bot）"),
) -> dict[str, Any]:
    require_non_guest(request)
    try:
        bot = get_bot_config(database_path, bot_key)
        if not bot:
            raise NotFoundError("Bot 未找到")

        warnings: list[str] = []
        purpose = str(payload.get("purpose") or "").strip().lower()
        if purpose != "bind":
            agent_provider = str(bot.get("agent_provider") or "").strip()
            if not agent_provider:
                warnings.append("该Bot未挂载Agent，启动后只能手动回复。")

        settings = get_bot_runtime_settings(database_path, bot_key=bot_key)
        validate_settings(settings, require_bot_credentials=True)
        status_after = manager.start(bot_key)
        return {
            "bot": status_after,
            "warnings": warnings,
        }
    except AppError:
        raise
    except Exception as exc:
        raise ConfigError("Bot服务启动失败", detail=str(exc)) from exc


@router.post("/{bot_key}/stop", summary="停止 Bot 服务", description="停止指定的 Bot 服务，会发送关闭消息给活跃会话")
def stop_named_bot(
    request: Request,
    bot_key: str = FastAPIPath(..., description="Bot Key"),
    database_path: Path = Depends(get_database_path),
    manager: BotProcessManager = Depends(get_manager),
) -> dict[str, Any]:
    require_non_guest(request)
    bot = get_bot_config(database_path, bot_key)
    if not bot:
        raise NotFoundError("Bot 未找到")
    status = manager.status(bot_key)
    if status.get("running"):
        _send_shutdown_text_if_needed(
            bot_key=bot_key,
            database_path=database_path,
        )
    return {
        "bot": manager.stop(bot_key),
    }


@router.post("/{bot_key}/rebind", summary="重新绑定 Bot", description="标记 Bot 需要重新绑定企业微信")
def rebind_bot(
    request: Request,
    bot_key: str = FastAPIPath(..., description="Bot Key"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    mark_bot_rebinding(database_path, bot_key)
    mapping_counts = get_bot_mapping_counts(database_path, [bot_key])
    return {"ok": True, "bot": _bot_api_view(get_bot_config(database_path, bot_key), mapping_counts=mapping_counts)}


@router.post("/{bot_key}/unbind", summary="解绑 Bot", description="解绑指定的 Bot，会先停止服务")
def unbind_named_bot(
    request: Request,
    bot_key: str = FastAPIPath(..., description="Bot Key"),
    database_path: Path = Depends(get_database_path),
    manager: BotProcessManager = Depends(get_manager),
) -> dict[str, Any]:
    require_non_guest(request)
    manager.stop(bot_key)
    unbind_bot(database_path, bot_key)
    mapping_counts = get_bot_mapping_counts(database_path, [bot_key])
    return {"ok": True, "bot": _bot_api_view(get_bot_config(database_path, bot_key), mapping_counts=mapping_counts)}


@router.get("/{bot_key}/skills", summary="获取 Bot 的 Skill 映射", description="获取指定 Bot 已挂载和可用的 Skill 列表")
def get_bot_skills(
    bot_key: str = FastAPIPath(..., description="Bot Key"),
    database_path: Path = Depends(get_database_path),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    bot = get_bot_config(database_path, bot_key)
    if bot is None:
        raise NotFoundError("Bot 未找到")
    enabled_names = get_enabled_skill_names(database_path)
    display_names = get_skill_display_names(database_path)
    skills = scan_skills(project_root, enabled_names, display_names)
    sync_skill_catalog(database_path, skills)
    enabled_skills = [s for s in skills if s.get("enabled") and str(s.get("scope") or "bot") == "bot"]
    checked_skills = get_bot_skill_mappings(database_path, bot_key)
    return {
        "all_skills": enabled_skills,
        "checked_skill_names": checked_skills,
    }


@router.post("/{bot_key}/skills", summary="保存 Bot 的 Skill 映射", description="更新指定 Bot 的 Skill 挂载关系，Bot 运行中无法修改")
def save_bot_skills(
    request: Request,
    bot_key: str = FastAPIPath(..., description="Bot Key"),
    payload: dict[str, Any] = Body(..., description="包含 skill_names 字段的对象：skill_names（字符串数组，要挂载的 Skill 名称列表）"),
    database_path: Path = Depends(get_database_path),
    manager: BotProcessManager = Depends(get_manager),
) -> dict[str, Any]:
    require_non_guest(request)
    bot = get_bot_config(database_path, bot_key)
    _ensure_bot_mapping_editable(bot=bot, manager=manager)
    skill_names = payload.get("skill_names", [])
    if not isinstance(skill_names, list):
        raise ValidationError("skill_names 必须是数组")
    enabled_names = set(get_enabled_skill_names(database_path))
    filtered = [str(n).strip() for n in skill_names if str(n).strip() in enabled_names]
    save_bot_skill_mappings(database_path, bot_key, filtered)
    mapping_counts = get_bot_mapping_counts(database_path, [bot_key])
    return {"ok": True, "bot": _bot_api_view(get_bot_config(database_path, bot_key), mapping_counts=mapping_counts)}


@router.get("/{bot_key}/mcp", summary="获取 Bot 的 MCP 映射", description="获取指定 Bot 已挂载和可用的 MCP 服务器列表")
def get_bot_mcp(
    bot_key: str = FastAPIPath(..., description="Bot Key"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    bot = get_bot_config(database_path, bot_key)
    if bot is None:
        raise NotFoundError("Bot 未找到")
    all_servers = list_mcp_servers(database_path)
    enabled_servers = [
        s for s in all_servers
        if s.get("is_active") and str(s.get("scope") or "bot") == "bot"
    ]
    checked_server_ids = get_bot_mcp_mappings(database_path, bot_key)
    return {
        "all_servers": enabled_servers,
        "checked_server_ids": checked_server_ids,
    }


@router.post("/{bot_key}/mcp", summary="保存 Bot 的 MCP 映射", description="更新指定 Bot 的 MCP 服务器挂载关系，Bot 运行中无法修改")
def save_bot_mcp(
    request: Request,
    bot_key: str = FastAPIPath(..., description="Bot Key"),
    payload: dict[str, Any] = Body(..., description="包含 server_ids 字段的对象：server_ids（字符串数组，要挂载的 MCP 服务器 ID 列表）"),
    database_path: Path = Depends(get_database_path),
    manager: BotProcessManager = Depends(get_manager),
) -> dict[str, Any]:
    require_non_guest(request)
    bot = get_bot_config(database_path, bot_key)
    _ensure_bot_mapping_editable(bot=bot, manager=manager)
    server_ids = payload.get("server_ids", [])
    if not isinstance(server_ids, list):
        raise ValidationError("server_ids 必须是数组")
    active_server_ids = {
        s["server_id"]
        for s in list_mcp_servers(database_path)
        if s.get("is_active") and str(s.get("scope") or "bot") == "bot"
    }
    filtered = [str(sid).strip() for sid in server_ids if str(sid).strip() in active_server_ids]
    save_bot_mcp_mappings(database_path, bot_key, filtered)
    mapping_counts = get_bot_mapping_counts(database_path, [bot_key])
    return {"ok": True, "bot": _bot_api_view(get_bot_config(database_path, bot_key), mapping_counts=mapping_counts)}


@router.post("/{bot_key}/read-all", summary="标记所有会话为已读", description="标记指定 Bot 的所有会话为已读状态")
def read_all_bot_chats(
    request: Request,
    bot_key: str = FastAPIPath(..., description="Bot Key"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    count = mark_all_bot_conversations_read(bot_key=bot_key, database_path=database_path)
    return {"ok": True, "count": count}
