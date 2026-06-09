from __future__ import annotations

from pathlib import Path
from typing import Any

from fastapi import APIRouter, Body, Depends, Query, Request

from app.api_response import ApiError
from app.bot_process_manager import BotProcessManager
from app.database import get_database_overview
from app.db.log_store import list_project_logs
from app.db.settings_store import get_platform_settings, upsert_platform_settings
from app.db.task_store import ensure_default_periodic_tasks, ensure_agent_dependent_tasks, has_enabled_agent_dependent_tasks, get_enabled_agent_dependent_tasks
from app.db.token_usage_store import get_token_usage_summary
from app.routers._deps import get_database_path, get_manager
from app.routers.auth import require_non_guest
from app.task_runtime import run_database_cleanup_task

router = APIRouter(prefix="/api", tags=["data"])


@router.get("/platform-settings", summary="获取平台设置", description="获取平台级别的全局设置")
def get_platform_settings_endpoint() -> dict[str, Any]:
    return {"settings": get_platform_settings()}


@router.post("/platform-settings", summary="更新平台设置", description="更新平台级别的全局设置")
def update_platform_settings(
    request: Request,
    payload: dict[str, Any] = Body(..., description="平台设置对象，包含 context_length_limit、platform_agent_timeout_seconds 等字段"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    str_fields = {
        "platform_agent_provider",
        "logging_level",
        "agent_truncation_notice",
        "agent_reply_notice",
        "agent_fallback_text",
    }
    int_fields = {
        "context_length_limit",
        "platform_agent_timeout_seconds",
        "platform_agent_max_iterations",
        "document_max_characters",
        "memory_update_max_pairs",
        "memory_update_max_chars",
        "thread_pool_max_workers",
        "agent_max_reasoning_chars",
        "agent_max_output_chars",
        "agent_max_stream_chunks",
        "agent_max_image_bytes",
        "agent_max_video_bytes",
        "agent_max_audio_bytes",
        "agent_max_file_bytes",
        "mcp_max_tool_event_payload_chars",
        "mcp_max_result_chars",
        "skills_max_script_output_chars",
        "agent_compression_transcript_max_chars",
        "agent_max_cache_size",
        "agent_recent_context_max_chars",
        "agent_recent_context_max_messages",
        "agent_recent_context_fetch_multiplier",
        "agent_context_message_max_chars",
        "agent_summary_in_prompt_max_chars",
        "agent_system_prompt_max_chars",
        "runtime_max_system_task_concurrency",
        "skills_max_tool_description_chars",
    }
    bool_fields = {
        "attachment_reply",
        "guest_account_enabled",
        "feedback_alert_enabled",
        "memory_query_expansion_enabled",
    }
    valid_log_levels = {"INFO", "WARNING", "ERROR"}
    for field in str_fields:
        if field in payload and not isinstance(payload[field], str):
            raise ApiError(f"{field} 必须是字符串", status_code=400)
    for field in int_fields:
        if field in payload and not isinstance(payload[field], int):
            raise ApiError(f"{field} 必须是整数", status_code=400)
    for field in bool_fields:
        if field in payload and not isinstance(payload[field], bool):
            raise ApiError(f"{field} 必须是布尔值", status_code=400)
    if "context_length_limit" in payload:
        value = int(payload["context_length_limit"])
        if value <= 0:
            raise ApiError("context_length_limit 必须大于 0", status_code=400)
    if "agent_max_reasoning_chars" in payload:
        value = int(payload["agent_max_reasoning_chars"])
        if value < 100:
            raise ApiError("agent_max_reasoning_chars 必须大于等于 100", status_code=400)
    if "document_max_characters" in payload:
        value = int(payload["document_max_characters"])
        if value < 500 or value > 500000:
            raise ApiError("document_max_characters 必须在 500 到 500000 之间", status_code=400)
    if "memory_update_max_pairs" in payload:
        value = int(payload["memory_update_max_pairs"])
        if value < 1 or value > 5000:
            raise ApiError("memory_update_max_pairs 必须在 1 到 5000 之间", status_code=400)
    if "memory_update_max_chars" in payload:
        value = int(payload["memory_update_max_chars"])
        if value < 1000 or value > 500000:
            raise ApiError("memory_update_max_chars 必须在 1000 到 500000 之间", status_code=400)
    if "agent_max_output_chars" in payload:
        value = int(payload["agent_max_output_chars"])
        if value < 100:
            raise ApiError("agent_max_output_chars 必须大于等于 100", status_code=400)
    if "agent_max_stream_chunks" in payload:
        value = int(payload["agent_max_stream_chunks"])
        if value < 10:
            raise ApiError("agent_max_stream_chunks 必须大于等于 10", status_code=400)
    for field in (
        "agent_max_image_bytes",
        "agent_max_video_bytes",
        "agent_max_audio_bytes",
        "agent_max_file_bytes",
    ):
        if field in payload:
            value = int(payload[field])
            if value < 0:
                raise ApiError(f"{field} 必须大于等于 0", status_code=400)
    if "mcp_max_tool_event_payload_chars" in payload:
        value = int(payload["mcp_max_tool_event_payload_chars"])
        if value < 100 or value > 10000:
            raise ApiError("mcp_max_tool_event_payload_chars 必须在 100 到 10000 之间", status_code=400)
    if "mcp_max_result_chars" in payload:
        value = int(payload["mcp_max_result_chars"])
        if value < 100 or value > 20000:
            raise ApiError("mcp_max_result_chars 必须在 100 到 20000 之间", status_code=400)
    if "skills_max_script_output_chars" in payload:
        value = int(payload["skills_max_script_output_chars"])
        if value < 100 or value > 20000:
            raise ApiError("skills_max_script_output_chars 必须在 100 到 20000 之间", status_code=400)
    if "platform_agent_timeout_seconds" in payload:
        value = int(payload["platform_agent_timeout_seconds"])
        if value < 10 or value > 1800:
            raise ApiError("platform_agent_timeout_seconds 必须在 10 到 1800 之间", status_code=400)
    if "platform_agent_max_iterations" in payload:
        value = int(payload["platform_agent_max_iterations"])
        if value < 1 or value > 50:
            raise ApiError("platform_agent_max_iterations 必须在 1 到 50 之间", status_code=400)
    if "thread_pool_max_workers" in payload:
        value = int(payload["thread_pool_max_workers"])
        if value < 10 or value > 30:
            raise ApiError("thread_pool_max_workers 必须在 10 到 30 之间", status_code=400)
    ranges = {
        "agent_compression_transcript_max_chars": (1000, 50000),
        "agent_max_cache_size": (1, 100),
        "agent_recent_context_max_chars": (500, 50000),
        "agent_recent_context_max_messages": (1, 100),
        "agent_recent_context_fetch_multiplier": (1, 10),
        "agent_context_message_max_chars": (100, 10000),
        "agent_summary_in_prompt_max_chars": (100, 10000),
        "agent_system_prompt_max_chars": (100, 100000),
        "runtime_max_system_task_concurrency": (1, 100),
        "skills_max_tool_description_chars": (100, 50000),
    }
    for field, (min_value, max_value) in ranges.items():
        if field in payload:
            value = int(payload[field])
            if value < min_value or value > max_value:
                raise ApiError(f"{field} 必须在 {min_value} 到 {max_value} 之间", status_code=400)
    if "logging_level" in payload:
        value = str(payload["logging_level"]).upper()
        if value not in valid_log_levels:
            raise ApiError(f"logging_level 必须是以下值之一: {', '.join(valid_log_levels)}", status_code=400)
    platform_agent_provider = str(payload.get("platform_agent_provider") or "").strip()
    old_provider = str(get_platform_settings().get("platform_agent_provider") or "").strip()
    if not platform_agent_provider and old_provider:
        if has_enabled_agent_dependent_tasks(database_path):
            raise ApiError(
                "平台 Agent 还有任务挂载，不允许清除。请先前往「任务管理」停用相关任务后再操作。",
                status_code=400,
                log_detail="存在启用状态的系统任务依赖平台 Agent",
            )
    result = upsert_platform_settings(payload)
    if platform_agent_provider:
        ensure_default_periodic_tasks(database_path)
        ensure_agent_dependent_tasks(database_path)
    return {"settings": result}


@router.get("/project-logs", summary="获取项目日志", description="获取项目的运行日志，支持按分类、级别、时间范围等筛选")
def get_project_logs(
    category: str = Query("", description="日志分类"),
    level: str = Query("", description="日志级别（INFO、WARN、ERROR）"),
    trace_id: str = Query("", description="追踪 ID"),
    start_time: str = Query("", description="开始时间（ISO 格式）"),
    end_time: str = Query("", description="结束时间（ISO 格式）"),
    page: int = Query(1, description="页码"),
    page_size: int = Query(20, description="每页数量"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    return list_project_logs(
        database_path,
        category=category.strip() if category else "",
        level=level.strip() if level else "",
        trace_id=trace_id.strip() if trace_id else "",
        start_time=start_time.strip() if start_time else "",
        end_time=end_time.strip() if end_time else "",
        page=page,
        page_size=page_size,
    )


@router.get("/data/overview", summary="获取数据概览", description="获取数据库的总体使用情况和统计信息")
def get_data_overview(
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    return get_database_overview(database_path)


@router.get("/data/token-usage", summary="获取 Token 使用统计", description="获取 Agent 的 Token 使用情况统计")
def get_token_usage(
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    return get_token_usage_summary(database_path)


@router.post("/data/optimize", summary="优化数据库", description="执行数据库清理和优化任务，清理过期数据")
def optimize_data(
    request: Request,
    database_path: Path = Depends(get_database_path),
    manager: BotProcessManager = Depends(get_manager),
) -> dict[str, Any]:
    require_non_guest(request)
    result = run_database_cleanup_task(
        database_path,
        manager,
        source="data_management",
        category="data",
    )
    return {"ok": True, "result": result}
