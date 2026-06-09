from __future__ import annotations

import json
from typing import Any

from fastapi import APIRouter, Body, Depends, Request
from pathlib import Path

from app.api_response import ApiError
from app.db.bot_store import list_bot_configs
from app.memory_update_builder import build_memory_update_preview
from app.db.task_store import (
    MEMORY_UPDATE_REVIEW_REQUIRED_PREFIX,
    DEFAULT_CHAT_MEMORY_REVIEW_PROMPT,
    DEFAULT_DOCUMENT_MEMORY_REVIEW_PROMPT,
    list_one_time_tasks,
    list_periodic_tasks,
    create_periodic_task,
    create_one_time_task,
    delete_periodic_task,
    disable_periodic_task,
    enable_periodic_task,
    get_periodic_task,
    mark_periodic_task_finished,
    update_periodic_task,
    trigger_task_now,
)
from app.db.memory_usage_audit_store import list_recent_memory_usage_audits
from app.db.ai_work_store import clear_ai_work_item_by_id, get_ai_work_task_by_id
from app.routers._deps import get_database_path, get_project_root
from app.routers.auth import require_admin, require_non_guest
from app.task_runtime import ensure_task_runtime

router = APIRouter(prefix="/api/tasks", tags=["tasks"])


def _normalize_string_list(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    items: list[str] = []
    for item in value:
        text = str(item or "").strip()
        if text:
            items.append(text)
    return items


def _find_latest_review_report(reviews_dir: Path, is_chat: bool) -> Path | None:
    if not reviews_dir.is_dir():
        return None
    target_title = "会话记忆使用审核" if is_chat else "文档记忆使用审核"
    candidates: list[Path] = []
    for f in reviews_dir.iterdir():
        if not f.is_file() or f.suffix != ".md":
            continue
        try:
            first_line = f.read_text(encoding="utf-8").split("\n", 1)[0]
            if target_title in first_line:
                candidates.append(f)
        except Exception:
            continue
    if not candidates:
        return None
    candidates.sort(key=lambda p: p.stat().st_mtime, reverse=True)
    return candidates[0]


def _parse_bot_task_payload(prompt_text: Any) -> dict[str, Any]:
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


def _build_bot_task_prompt_text(
    prompt_text: Any,
    *,
    skill_names: Any = None,
    mcp_server_ids: Any = None,
) -> str:
    payload = _parse_bot_task_payload(prompt_text)
    if skill_names is not None:
        payload["skill_names"] = _normalize_string_list(skill_names)
    if mcp_server_ids is not None:
        payload["mcp_server_ids"] = _normalize_string_list(mcp_server_ids)
    return json.dumps(payload, ensure_ascii=False)


def _resolve_mcp_server_names(database_path: Path, server_ids: list[str]) -> list[dict[str, str]]:
    requested = [str(item or "").strip() for item in server_ids if str(item or "").strip()]
    if not requested:
        return []
    placeholders = ",".join("?" for _ in requested)
    from app.db.core import connect_database

    with connect_database(database_path) as conn:
        rows = conn.execute(
            f"""
            SELECT server_id, name
            FROM mcp_server_config
            WHERE server_id IN ({placeholders})
            """,
            requested,
        ).fetchall()
    by_id = {str(row["server_id"]): str(row["name"] or row["server_id"]) for row in rows}
    return [
        {
            "server_id": server_id,
            "name": by_id.get(server_id, server_id),
        }
        for server_id in requested
    ]


def _enrich_bot_task_refs(task: dict[str, Any], database_path: Path) -> dict[str, Any]:
    if not isinstance(task, dict):
        return task
    if str(task.get("executor_kind") or "") != "bot" and str(task.get("handler_name") or "") != "bot_task":
        return task
    payload = _parse_bot_task_payload(task.get("prompt_text"))
    servers = _resolve_mcp_server_names(database_path, payload.get("mcp_server_ids") or [])
    task["skill_names"] = payload.get("skill_names") or []
    task["mcp_server_ids"] = payload.get("mcp_server_ids") or []
    task["mcp_servers"] = servers
    task["mcp_server_names"] = [item["name"] for item in servers]
    return task


def _enrich_task_list_refs(result: dict[str, Any], database_path: Path) -> dict[str, Any]:
    tasks = result.get("tasks")
    if isinstance(tasks, list):
        for task in tasks:
            if isinstance(task, dict):
                _enrich_bot_task_refs(task, database_path)
    return result


def _build_review_mode_prompt(*, is_chat: bool, mode: str, base_prompt: str) -> str:
    subject = "会话记忆" if is_chat else "文档记忆"
    if mode == "review":
        suffix = "当前模式：仅审查。只输出审查报告、问题列表和建议，不生成会被应用的补丁，不修改任何记忆文件。"
    elif mode == "dry_run":
        suffix = "当前模式：预览补丁。可以生成 recommended_patches 作为修复预案，但只做 dry run 预演，不修改任何记忆文件。"
    else:
        suffix = "当前模式：自动修复。可以为安全且明确的问题生成 recommended_patches；只有后端收到显式确认时才允许应用补丁。"
    return f"{base_prompt.rstrip()}\n\n{suffix}\n审查对象：{subject}。"


@router.get("", summary="获取任务列表", description="统一获取任务列表，支持周期任务、一次性任务和全部任务的筛选与分页")
def get_tasks(
    scope: str = "",
    keyword: str = "",
    status: str = "",
    task_type: str = "",
    page: int = 1,
    page_size: int = 10,
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    ensure_task_runtime(database_path)
    normalized_type = str(task_type or "").strip().lower()
    if normalized_type == "periodic":
        return _enrich_task_list_refs(
            list_periodic_tasks(
                database_path,
                scope=scope,
                keyword=keyword,
                status=status,
                task_type=normalized_type,
                page=page,
                page_size=page_size,
            ),
            database_path,
        )
    if normalized_type == "one_time":
        return _enrich_task_list_refs(
            list_one_time_tasks(
                database_path,
                scope=scope,
                keyword=keyword,
                status=status,
                page=page,
                page_size=page_size,
            ),
            database_path,
        )

    combined_page_size = max(5000, page * page_size * 4)
    periodic = list_periodic_tasks(
        database_path,
        scope=scope,
        keyword=keyword,
        status=status,
        task_type="",
        page=1,
        page_size=combined_page_size,
    )
    one_time = list_one_time_tasks(
        database_path,
        scope=scope,
        keyword=keyword,
        status=status,
        page=1,
        page_size=combined_page_size,
    )
    periodic_tasks = sorted(
        periodic.get("tasks") or [],
        key=lambda task: (
            0 if str(task.get("task_scope") or "") == "system" else 1,
            str(task.get("next_run_at") or "9999-12-31T23:59:59+08:00"),
            str(task.get("task_key") or ""),
        ),
    )
    one_time_tasks = sorted(
        one_time.get("tasks") or [],
        key=lambda task: (
            0 if str(task.get("task_scope") or "") == "system" else 1,
            str(task.get("created_at") or task.get("updated_at") or task.get("started_at") or ""),
            str(task.get("task_key") or ""),
        ),
        reverse=True,
    )
    merged_tasks = [*periodic_tasks, *one_time_tasks]
    current_page = max(1, int(page or 1))
    current_page_size = max(1, int(page_size or 10))
    total = len(merged_tasks)
    offset = (current_page - 1) * current_page_size
    paged_tasks = merged_tasks[offset: offset + current_page_size]
    total_pages = (total + current_page_size - 1) // current_page_size if total else 1
    return _enrich_task_list_refs({
        "tasks": paged_tasks,
        "total": total,
        "page": current_page,
        "page_size": current_page_size,
        "total_pages": total_pages,
    }, database_path)


@router.get("/periodic", summary="获取周期任务列表", description="获取所有周期性定时任务列表，支持按范围、关键字、状态、类型筛选和分页")
def get_periodic_tasks(
    scope: str = "",
    keyword: str = "",
    status: str = "",
    task_type: str = "",
    page: int = 1,
    page_size: int = 10,
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    ensure_task_runtime(database_path)
    return _enrich_task_list_refs(
        list_periodic_tasks(
            database_path,
            scope=scope,
            keyword=keyword,
            status=status,
            task_type=task_type,
            page=page,
            page_size=page_size,
        ),
        database_path,
    )


@router.get("/one-time", summary="获取一次性任务列表", description="获取所有一次性定时任务列表，支持按范围、关键字、状态筛选和分页")
def get_one_time_tasks(
    scope: str = "",
    keyword: str = "",
    status: str = "",
    page: int = 1,
    page_size: int = 10,
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    return _enrich_task_list_refs(
        list_one_time_tasks(
            database_path,
            scope=scope,
            keyword=keyword,
            status=status,
            page=page,
            page_size=page_size,
        ),
        database_path,
    )


@router.get("/executors", summary="获取任务执行器列表", description="获取可用的任务执行器列表，包括已启用的 Bot，用于创建任务时选择执行器")
def get_task_executors(
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    """获取任务执行器列表（包括已启用的 Bot）"""
    # 获取Bot列表，只返回已启用的
    bots_result = list_bot_configs(database_path)
    bots = []
    for bot in bots_result:
        if bot.get("is_active"):
            bots.append({
                "type": "bot",
                "id": bot.get("bot_key"),
                "name": bot.get("name"),
            })
    
    # 新建任务只支持 Bot 执行器；系统底层任务使用平台 Agent 但不在创建入口暴露。
    agents = []
    
    return {
        "bots": bots,
        "agents": agents,
    }


@router.get("/{task_key}", summary="获取任务详情", description="获取指定任务的详细信息，包括调度配置、执行状态、上次运行结果等。")
def get_task_detail(
    task_key: str,
    database_path: Path = Depends(get_database_path),
    project_root: Path = Depends(get_project_root),
) -> dict[str, Any]:
    ensure_task_runtime(database_path)
    task = get_periodic_task(database_path, task_key=task_key)
    if task is None:
        task = get_ai_work_task_by_id(database_path, task_key)
        if task is None:
            raise ApiError("任务不存在", status_code=404)
    _enrich_bot_task_refs(task, database_path)
    
    result = {"task": task}
    
    if task.get("handler_name") == "memory_update":
        preview_cutoff_time = None
        if task.get("prompt_text"):
            try:
                prompt_data = json.loads(str(task.get("prompt_text") or "{}"))
                preview_cutoff_time = str(prompt_data.get("cutoff_time") or "").strip() or None
            except (json.JSONDecodeError, TypeError, ValueError):
                preview_cutoff_time = None
        preview_data = build_memory_update_preview(database_path, cutoff_time=preview_cutoff_time)
        
        if not task.get("prompt_text") or task.get("prompt_text") == "":
            result["task"]["prompt_text"] = json.dumps(preview_data["payload"], ensure_ascii=False)
        
        result["memory_update_preview"] = preview_data
    
    elif task.get("handler_name") == "document_memory_extraction":
        from app.db.document_store import get_document_by_id
        from app.document_text_extractor import extract_text_from_file
        
        prompt_data = {}
        try:
            prompt_data = json.loads(str(task.get("prompt_text") or "{}"))
        except (json.JSONDecodeError, ValueError):
            pass
        
        doc_id = prompt_data.get("doc_id", "")
        if doc_id:
            doc = get_document_by_id(database_path, doc_id)
            if doc:
                doc_preview = {
                    "doc_id": doc_id,
                    "filename": doc.get("filename", ""),
                    "file_type": doc.get("file_type", ""),
                    "file_size": doc.get("file_size", 0),
                    "parse_status": doc.get("parse_status", ""),
                    "convert_status": doc.get("convert_status", ""),
                    "content": "",
                    "error": "",
                }
                storage_path = Path(doc.get("storage_path", ""))
                if not storage_path.exists():
                    doc_preview["error"] = f"文件不存在: {storage_path}"
                else:
                    try:
                        file_bytes = storage_path.read_bytes()
                        doc_preview["content"] = extract_text_from_file(file_bytes, doc.get("file_type", ""))
                        if not doc_preview["content"]:
                            doc_preview["error"] = "无法提取文件内容，文件格式可能不受支持或内容为空"
                    except Exception as e:
                        doc_preview["error"] = f"提取文件内容失败: {e}"
                result["document_preview"] = doc_preview

    elif task.get("handler_name") in ("self_review_chat_memory", "self_review_document_memory"):
        reviews_dir = project_root / ".memory" / "reviews"
        is_chat = task.get("handler_name") == "self_review_chat_memory"
        report_path = _find_latest_review_report(reviews_dir, is_chat)
        result["review_report"] = {
            "path": str(report_path) if report_path else "",
            "content": report_path.read_text(encoding="utf-8") if report_path and report_path.exists() else "",
        }
        default_prompt_json = DEFAULT_CHAT_MEMORY_REVIEW_PROMPT if is_chat else DEFAULT_DOCUMENT_MEMORY_REVIEW_PROMPT
        default_prompt_data = json.loads(default_prompt_json)
        base_prompt = str(default_prompt_data.get("review_prompt", "") or "")
        result["review_mode_config"] = {
            "modes": {
                "review": {
                    "label": "仅审查",
                    "description": "审查会话记忆的使用效果，仅出审查报告不做修改" if is_chat else "审查文档记忆的写入质量和使用效果，仅出审查报告不做修改",
                    "prompt": _build_review_mode_prompt(is_chat=is_chat, mode="review", base_prompt=base_prompt),
                },
                "dry_run": {
                    "label": "预览补丁",
                    "description": "审查会话记忆的使用效果，预览修复补丁但不实际写入" if is_chat else "审查文档记忆的写入质量和使用效果，预览修复补丁但不实际写入",
                    "prompt": _build_review_mode_prompt(is_chat=is_chat, mode="dry_run", base_prompt=base_prompt),
                },
                "patch": {
                    "label": "自动修复",
                    "description": "审查会话记忆的使用效果，自动应用安全补丁修复问题" if is_chat else "审查文档记忆的写入质量和使用效果，自动应用安全补丁修复问题",
                    "prompt": _build_review_mode_prompt(is_chat=is_chat, mode="patch", base_prompt=base_prompt),
                },
            },
            "default_prompt": default_prompt_data.get("review_prompt", ""),
        }
    elif task.get("handler_name") == "explicit_memory":
        explicit_preview = {
            "source_text": "",
            "metadata": {},
        }
        try:
            prompt_data = json.loads(str(task.get("prompt_text") or "{}"))
            if isinstance(prompt_data, dict):
                explicit_preview["source_text"] = str(prompt_data.get("source_text") or "")
                metadata = prompt_data.get("metadata") or {}
                explicit_preview["metadata"] = metadata if isinstance(metadata, dict) else {}
        except (json.JSONDecodeError, ValueError):
            explicit_preview["source_text"] = str(task.get("prompt_text") or "")
        result["explicit_memory_preview"] = explicit_preview
    elif task.get("handler_name") == "bot_task":
        result["bot_task_preview"] = _parse_bot_task_payload(task.get("prompt_text"))

    return result


@router.post("/{task_key}/enable", summary="启用任务", description="启用指定的周期任务，正在运行中的任务不允许操作")
def enable_task(
    request: Request,
    task_key: str,
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    ensure_task_runtime(database_path)
    task = get_periodic_task(database_path, task_key=task_key)
    if task is None:
        raise ApiError("任务不存在", status_code=404)
    if task["task_type"] != "periodic":
        raise ApiError("只能启用周期任务", status_code=400)
    if (
        task.get("handler_name") == "memory_update"
        and str(task.get("last_run_message") or "").startswith(MEMORY_UPDATE_REVIEW_REQUIRED_PREFIX)
    ):
        raise ApiError("当前记忆更新任务仍有未处理批次，请先在任务详情中手动执行当前批次", status_code=400)
    ok = enable_periodic_task(database_path, task_key=task_key)
    if not ok:
        raise ApiError("启用失败，任务可能已启用或状态不允许", status_code=400)
    return {"ok": True}


@router.post("/{task_key}/disable", summary="停用任务", description="停用指定的周期任务，正在运行中的任务不允许操作")
def disable_task(
    request: Request,
    task_key: str,
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    ensure_task_runtime(database_path)
    task = get_periodic_task(database_path, task_key=task_key)
    if task is None:
        raise ApiError("任务不存在", status_code=404)
    if task["task_type"] != "periodic":
        raise ApiError("只能停用周期任务", status_code=400)
    ok = disable_periodic_task(database_path, task_key=task_key)
    if not ok:
        raise ApiError("停用失败，任务可能已停用或正在执行", status_code=400)
    return {"ok": True}


@router.put("/{task_key}", summary="编辑任务", description="编辑指定任务的配置，系统级任务（除记忆更新和文档提取外）不允许编辑，启用中的周期任务需先停用才能编辑")
def edit_task(
    request: Request,
    task_key: str,
    payload: dict[str, Any] = Body(..., description="任务编辑字段：name（名称）、description（描述）、executor_kind（执行器类型）、executor_id（执行器ID）、schedule_type（调度类型）、schedule_value（调度值）、schedule_time（调度时间）、prompt_text（提示文本）、skill_names（技能名称列表）、mcp_server_ids（MCP服务器ID列表）、task_type（任务类型）"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    ensure_task_runtime(database_path)
    task = get_periodic_task(database_path, task_key=task_key)
    if task is None:
        raise ApiError("任务不存在", status_code=404)
    # 记忆更新、文档提取和记忆审查任务允许编辑
    is_editable_system_task = task["task_scope"] == "system" and task.get("handler_name") in ["memory_update", "document_memory_extraction", "self_review_chat_memory", "self_review_document_memory"]
    if task["task_scope"] == "system" and not is_editable_system_task:
        raise ApiError("系统级任务不允许编辑", status_code=403)
    if task["task_type"] == "periodic" and task["is_enabled"] and not is_editable_system_task:
        raise ApiError("周期任务启用中不允许编辑，请先停用", status_code=400)
    
    # 处理prompt_text和skill/mcp选择
    executor_kind = str(payload.get("executor_kind", task.get("executor_kind")) or "").strip()
    if executor_kind and executor_kind not in ["builtin", "bot", "platform_agent"]:
        raise ApiError("无效的执行器类型", status_code=400)
    prompt_text = payload.get("prompt_text", task.get("prompt_text"))
    handler_name = task.get("handler_name", "")
    
    # 如果是bot_task或当前编辑成bot执行器，重新组装prompt_text为JSON
    if handler_name == "bot_task" or executor_kind == "bot":
        skill_names = payload.get("skill_names") if "skill_names" in payload else None
        mcp_server_ids = payload.get("mcp_server_ids") if "mcp_server_ids" in payload else None
        prompt_text = _build_bot_task_prompt_text(
            prompt_text,
            skill_names=skill_names,
            mcp_server_ids=mcp_server_ids,
        )
    
    ok = update_periodic_task(
        database_path,
        task_key=task_key,
        name=payload.get("name"),
        description=payload.get("description"),
        executor_kind=payload.get("executor_kind"),
        executor_id=payload.get("executor_id"),
        schedule_type=payload.get("schedule_type"),
        schedule_value=payload.get("schedule_value"),
        schedule_time=payload.get("schedule_time"),
        prompt_text=prompt_text,
        task_type=payload.get("task_type"),
        notify_bot_key=payload.get("notify_bot_key"),
    )
    if not ok:
        raise ApiError("编辑失败", status_code=400)
    updated = get_periodic_task(database_path, task_key=task_key)
    return {"ok": True, "task": updated}


@router.delete("/{task_key}", summary="删除任务", description="删除指定的任务，系统核心任务和执行中的任务不允许删除，启用中的周期任务需先停用才能删除")
def delete_task(
    request: Request,
    task_key: str,
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_admin(request)
    ensure_task_runtime(database_path)
    task = get_periodic_task(database_path, task_key=task_key)
    if task is None:
        ai_work_task = get_ai_work_task_by_id(database_path, task_key)
        if ai_work_task is None:
            raise ApiError("任务不存在", status_code=404)
        if clear_ai_work_item_by_id(database_path, task_key):
            return {"ok": True}
        raise ApiError("任务状态不允许删除", status_code=400)
    ok, error_msg = delete_periodic_task(database_path, task_key=task_key)
    if not ok:
        status_code = 403 if "核心" in error_msg else 400
        raise ApiError(error_msg or "删除失败", status_code=status_code)
    return {"ok": True}


@router.post("", summary="创建任务", description="创建新的定时任务，支持周期任务和一次性任务，执行器仅支持 bot")
def create_task(
    request: Request,
    payload: dict[str, Any] = Body(..., description="新建任务字段：name（名称，必填）、task_type（类型：periodic/one_time）、executor_kind（执行器类型：bot）、executor_id（执行器ID，bot时必填）、schedule_type（调度类型）、schedule_value（调度值）、schedule_time（调度时间）、prompt_text（提示文本）、execute_at（一次性任务执行时间）、skill_names（技能名称列表）、mcp_server_ids（MCP服务器ID列表）"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    ensure_task_runtime(database_path)
    name = str(payload.get("name", "")).strip()
    if not name:
        raise ApiError("任务名称不能为空", status_code=400)
    
    task_type = str(payload.get("task_type", "periodic")).strip().lower()
    
    executor_kind = str(payload.get("executor_kind") or "bot").strip()
    if executor_kind != "bot":
        raise ApiError("新建任务只支持 Bot 执行器", status_code=400)
    
    if executor_kind == "bot":
        if not payload.get("executor_id"):
            raise ApiError("Bot 类型需要指定执行器ID", status_code=400)
    
    # 处理prompt_text和skill/mcp选择
    handler_name = str(payload.get("handler_name", "")).strip()
    prompt_text = payload.get("prompt_text", "")
    
    # 如果是bot执行器，自动设置handler为bot_task，并组装prompt_text为JSON
    if executor_kind == "bot":
        handler_name = "bot_task"
        skill_names = payload.get("skill_names") if "skill_names" in payload else None
        mcp_server_ids = payload.get("mcp_server_ids") if "mcp_server_ids" in payload else None
        prompt_text = _build_bot_task_prompt_text(
            prompt_text,
            skill_names=skill_names,
            mcp_server_ids=mcp_server_ids,
        )
    
    if task_type == "one_time":
        task = create_one_time_task(
            database_path,
            name=name,
            description=payload.get("description", ""),
            executor_kind=executor_kind,
            executor_id=payload.get("executor_id", ""),
            handler_name=handler_name,
            prompt_text=prompt_text,
            execute_at=payload.get("execute_at", ""),
        )
    else:
        # 创建周期任务
        task = create_periodic_task(
            database_path,
            name=name,
            description=payload.get("description", ""),
            executor_kind=executor_kind,
            executor_id=payload.get("executor_id", ""),
            handler_name=handler_name,
            schedule_type=payload.get("schedule_type", "interval_days"),
            schedule_value=payload.get("schedule_value", 1),
            schedule_time=payload.get("schedule_time", "00:00"),
            prompt_text=prompt_text,
            notify_bot_key=payload.get("notify_bot_key", ""),
        )
    
    if task is None:
        raise ApiError("创建任务失败", status_code=500)
    return {"ok": True, "task": task}


@router.post("/{task_key}/trigger", summary="立即触发任务", description="立即触发指定任务执行，将任务的 next_run_at 设置为当前时间，并调整相应状态")
def trigger_task(
    request: Request,
    task_key: str,
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    ensure_task_runtime(database_path)
    task = get_periodic_task(database_path, task_key=task_key)
    if task is None:
        raise ApiError("任务不存在", status_code=404)
    # 依赖平台Agent的任务，手动触发时检查平台Agent是否已配置
    if task.get("handler_name") == "document_memory_extraction":
        from app.db.document_store import get_document_by_id

        prompt_data: dict[str, Any] = {}
        try:
            prompt_data = json.loads(str(task.get("prompt_text") or "{}"))
        except (json.JSONDecodeError, TypeError, ValueError):
            prompt_data = {}
        doc_id = str(prompt_data.get("doc_id") or "").strip()
        if doc_id:
            doc = get_document_by_id(database_path, doc_id)
            if doc and str(doc.get("convert_status") or "").strip() == "converted":
                raise ApiError("该文档已完成转换，不允许再次发起提取任务", status_code=400)
    if task.get("handler_name") == "self_review_document_memory":
        audit_samples = list_recent_memory_usage_audits(
            database_path,
            days=7,
            call_types=("chat", "draft"),
            limit=1,
            require_documents=True,
        )
        if not audit_samples:
            summary = "文档记忆审查失败: 无文档记忆使用记录，无法执行审查"
            mark_periodic_task_finished(
                database_path,
                task_key=task_key,
                run_status="failed",
                message=summary,
            )
            updated = get_periodic_task(database_path, task_key=task_key)
            return {"ok": False, "task": updated, "summary": summary}
    from app.db.task_store import is_agent_dependent_handler
    if is_agent_dependent_handler(task.get("handler_name", "")):
        from app.db.settings_store import get_platform_settings
        provider = str(get_platform_settings().get("platform_agent_provider") or "").strip()
        if not provider:
            raise ApiError("请先在系统设置中选择平台 Agent", status_code=400)
    ok = trigger_task_now(database_path, task_key=task_key)
    if not ok:
        raise ApiError("触发任务失败", status_code=500)
    updated = get_periodic_task(database_path, task_key=task_key)
    return {"ok": True, "task": updated}
