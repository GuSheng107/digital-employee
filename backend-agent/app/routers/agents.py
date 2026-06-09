from __future__ import annotations

from typing import Any
from uuid import uuid4

from fastapi import APIRouter, Body, Depends, Path as FastAPIPath, Query, Request
from pathlib import Path

from agent_runtime.capabilities import detect_capabilities_api
from agent_runtime.models import build_chat_model
from agent_runtime.provider_fields import get_provider_param_schemas
from agent_runtime.service import _extract_message_content, _extract_usage_metadata
from app.api_response import ApiError
from app.config_loader import AgentProviderSettings
from app.db.agent_store import (
    SUPPORTED_PROVIDER_TYPES,
    get_agent,
    list_agents,
    set_agent_active,
    update_agent_test_status,
    upsert_agent,
)
from app.db.core import connect_database
from app.db.settings_store import load_settings_from_database, get_platform_settings
from app.exceptions import AppError, NotFoundError, ValidationError
from app.routers._deps import get_database_path
from app.routers._utils import _collect_agent_bot_usage, _enrich_bot_bound_item
from app.routers.auth import require_admin, require_non_guest
from app.utils import extract_error_info, format_error_message

router = APIRouter(prefix="/api/agents", tags=["agents"])

AGENT_TEST_PROMPT = (
    "Connectivity test. Reply exactly with OK. "
    "No punctuation, no explanation, max 1 token."
)


def _extract_connectivity_test_error(exc: Exception, request_info: dict) -> str:
    error_info = extract_error_info(exc)
    error_info["request_info"] = request_info
    return format_error_message(error_info)


def _assert_agent_edit_allowed(
    existing_agent: dict[str, Any],
    payload: dict[str, Any],
    usage: dict[str, Any] | None,
    is_platform_agent: bool = False,
) -> None:
    if not (is_platform_agent or (usage and usage["mounted_bot_count"] > 0)):
        return
    protected_fields = (
        "provider_type", "model", "base_url", "temperature",
        "timeout_seconds", "max_retries", "is_active",
        "last_test_status", "last_test_time", "last_test_trace_id",
    )
    changed_fields = []
    for field in protected_fields:
        if field not in payload:
            continue
        if str(payload.get(field, "")) != str(existing_agent.get(field, "")):
            changed_fields.append(field)
    if "api_key" in payload and str(payload.get("api_key", "")) != str(existing_agent.get("api_key", "")):
        changed_fields.append("api_key")
    if changed_fields:
        if is_platform_agent:
            raise ValidationError(
                f"Agent[{existing_agent.get('label', '')}]是平台默认 Agent，"
                "只能编辑名称和 Provider 名称"
            )
        else:
            raise ValidationError(
                f"Agent[{usage['item_label']}]已被 Bot[{', '.join(usage['mounted_bot_names'])}] 挂载，"
                "只能编辑名称和 Provider 名称"
            )


def _validate_agent_payload_before_save(
    payload: dict[str, Any],
    *,
    database_path: Path,
    provider_key: str,
    require_api_key: bool,
) -> None:
    provider_type = str(payload.get("provider_type") or "").strip()
    label = str(payload.get("label") or "").strip()
    model = str(payload.get("model") or "").strip()
    api_key = str(payload.get("api_key") or "").strip()
    base_url = str(payload.get("base_url") or "").strip()

    if not label:
        raise ValidationError("Agent 标签不能为空")
    if provider_type not in SUPPORTED_PROVIDER_TYPES:
        raise ValidationError(f"Provider 类型不支持: {provider_type}")
    if require_api_key and not api_key:
        raise ValidationError("API Key 不能为空")
    if not model:
        raise ValidationError("模型不能为空")
    if provider_type == "openai_compatible":
        if not base_url:
            raise ValidationError("Base URL 不能为空")

    with connect_database(database_path) as conn:
        duplicated = conn.execute(
            """
            SELECT provider_key
            FROM agent_provider_config
            WHERE lower(label) = lower(?) AND provider_key <> ?
            LIMIT 1
            """,
            (label, provider_key),
        ).fetchone()
    if duplicated:
        raise ValidationError("Agent 标签已存在，请使用唯一标签")


@router.get("", summary="获取 Agent 列表", description="获取所有 Agent 配置列表，支持分页和关键字搜索")
def get_agents(
    provider_key: str | None = Query(None, description="Provider Key，指定时获取单个 Agent 详情"),
    page: int = Query(1, description="页码"),
    page_size: int = Query(10, description="每页数量"),
    keyword: str = Query("", description="搜索关键字"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    if provider_key:
        agent = get_agent(database_path, provider_key)
        if agent is None:
            raise NotFoundError("Agent not found")
        usage_map = _collect_agent_bot_usage(database_path, [provider_key])
        return {"agent": _enrich_bot_bound_item(agent, usage_map.get(provider_key))}

    result = list_agents(database_path, page=page, page_size=page_size, keyword=keyword)
    provider_keys = [
        str(item.get("provider_key") or "").strip()
        for item in result.get("agents", [])
        if str(item.get("provider_key") or "").strip()
    ]
    usage_map = _collect_agent_bot_usage(database_path, provider_keys)
    result["agents"] = [
        _enrich_bot_bound_item(item, usage_map.get(str(item.get("provider_key") or "").strip()))
        for item in result.get("agents", [])
    ]
    return result


@router.post("", summary="创建或更新 Agent", description="创建新 Agent 或更新现有 Agent 配置，已挂载的 Agent 只能编辑名称")
def create_or_update_agent(
    request: Request,
    payload: dict[str, Any] = Body(..., description="Agent 配置对象，包含 mode（'new'或'edit'）、label、provider_type、model、api_key 等字段"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    mode = str(payload.get("mode", "new")).strip()

    if mode == "new":
        provider_key = str(uuid4())
        try:
            _validate_agent_payload_before_save(
                payload,
                database_path=database_path,
                provider_key=provider_key,
                require_api_key=True,
            )
            payload["is_active"] = False
            payload["last_test_status"] = ""
            payload["last_test_time"] = ""
            payload["last_test_trace_id"] = ""
            return {"agent": upsert_agent(database_path, provider_key, payload)}
        except Exception as exc:
            if isinstance(exc, (ApiError, AppError)):
                raise
            raise ValidationError("Agent 保存失败", detail=str(exc)) from exc
    elif mode == "edit":
        provider_key = str(payload.get("provider_key", "")).strip()
        if not provider_key:
            raise ValidationError("provider_key 不能为空")
        try:
            existing_agent = get_agent(database_path, provider_key)
            if existing_agent is None:
                raise NotFoundError("Agent 未找到")
            usage = _collect_agent_bot_usage(database_path, [provider_key]).get(provider_key)
            platform_settings = get_platform_settings()
            is_platform_agent = (platform_settings.get("platform_agent_provider", "") == provider_key)
            if is_platform_agent or (usage and usage["mounted_bot_count"] > 0):
                payload["is_active"] = existing_agent.get("is_active", False)
                payload["last_test_status"] = existing_agent.get("last_test_status", "")
                payload["last_test_time"] = existing_agent.get("last_test_time", "")
                payload["last_test_trace_id"] = existing_agent.get("last_test_trace_id", "")
            else:
                payload["is_active"] = False
                payload["last_test_status"] = ""
                payload["last_test_time"] = ""
                payload["last_test_trace_id"] = ""
            _assert_agent_edit_allowed(existing_agent, payload, usage, is_platform_agent)
            _validate_agent_payload_before_save(
                payload,
                database_path=database_path,
                provider_key=provider_key,
                require_api_key=False,
            )
            return {"agent": upsert_agent(database_path, provider_key, payload)}
        except Exception as exc:
            if isinstance(exc, (ApiError, AppError)):
                raise
            raise ValidationError("Agent 保存失败", detail=str(exc)) from exc
    else:
        raise ValidationError("无效的 mode 参数")


@router.get("/capabilities", summary="获取模型能力", description="检测指定模型的功能能力，如视觉、结构化输出等")
def get_model_capabilities_api(
    model: str = Query("", description="模型名称"),
    provider_type: str = Query("", description="Provider 类型"),
) -> dict[str, Any]:
    if not model:
        raise ValidationError("model 参数不能为空")
    if not provider_type:
        raise ValidationError("provider_type 参数不能为空")
    return detect_capabilities_api(model, provider_type)


@router.get("/provider-schemas", summary="获取 Provider 配置字段定义", description="获取所有支持的 Provider 的配置字段定义和说明")
def get_agent_provider_schemas_api() -> dict[str, Any]:
    return {"providers": get_provider_param_schemas()}


@router.post("/batch-delete", summary="批量删除 Agent", description="批量删除指定的 Agent，已被 Bot 挂载的 Agent 无法删除")
def batch_delete_agents_api(
    request: Request,
    payload: dict[str, Any] = Body(..., description="包含 provider_keys 字段的对象：provider_keys（字符串数组，要删除的 Provider Key 列表）"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_admin(request)
    provider_keys = payload.get("provider_keys", [])
    if not isinstance(provider_keys, list) or len(provider_keys) == 0:
        raise ValidationError("provider_keys 必须是非空列表")

    usage_map = _collect_agent_bot_usage(database_path, [str(item) for item in provider_keys])
    blocked = []
    for provider_key in provider_keys:
        usage = usage_map.get(str(provider_key))
        if usage and usage["mounted_bot_count"] > 0:
            blocked.append(
                f"Agent [{usage['item_label']}] 已被 Bot [{', '.join(usage['mounted_bot_names'])}] 挂载，无法删除"
            )
    if blocked:
        raise ValidationError('; '.join(blocked))

    deleted_count = 0
    with connect_database(database_path) as conn:
        for key in provider_keys:
            cursor = conn.execute("DELETE FROM agent_provider_config WHERE provider_key = ?", (key,))
            deleted_count += cursor.rowcount

    return {"ok": True, "deleted_count": deleted_count}


@router.post("/{provider_key}/toggle", summary="启用/禁用 Agent", description="启用或禁用指定 Agent，已挂载的 Agent 无法禁用，启用需要先通过连通性测试")
def toggle_agent_api(
    request: Request,
    provider_key: str = FastAPIPath(..., description="Provider Key"),
    payload: dict[str, Any] = Body(..., description="包含 is_active 字段的对象：is_active（布尔，true=启用，false=禁用）"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    is_active = bool(payload.get("is_active", False))
    
    platform_settings = get_platform_settings()
    is_platform_agent = (platform_settings.get("platform_agent_provider", "") == provider_key)
    
    if not is_active:
        usage = _collect_agent_bot_usage(database_path, [provider_key]).get(provider_key)
        if is_platform_agent:
            raise ValidationError(
                f"Agent 是平台默认 Agent，无法停用"
            )
        if usage and usage["mounted_bot_count"] > 0:
            raise ValidationError(
                f"Agent [{usage['item_label']}] 已被 Bot [{', '.join(usage['mounted_bot_names'])}] 挂载，无法禁用"
            )
    if is_active:
        agent = get_agent(database_path, provider_key)
        if not agent:
            raise NotFoundError("Agent 未找到")
        if agent.get("last_test_status") != "success":
            trace_id = agent.get("last_test_trace_id") or str(uuid4())
            raise ApiError(
                "Agent 必须先通过连通性测试后才能启用",
                status_code=400,
                trace_id=trace_id,
                log_message="Agent activation blocked by failed connectivity test.",
            )
    set_agent_active(database_path, provider_key, is_active)
    return {"ok": True, "is_active": is_active}


@router.post("/{provider_key}/test", summary="测试 Agent 连通性", description="测试指定 Agent 的连通性，成功后才能启用该 Agent")
async def test_single_agent(
    request: Request,
    provider_key: str = FastAPIPath(..., description="Provider Key"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    agent = get_agent(database_path, provider_key, decrypt_api_key=True)
    if not agent:
        raise NotFoundError("Agent 未找到")

    request_info = {
        "provider_type": agent["provider_type"],
        "model": agent["model"],
        "base_url": agent["base_url"],
        "timeout_seconds": min(int(agent["timeout_seconds"]), 15),
    }

    try:
        test_settings = load_settings_from_database(database_path)
        provider = AgentProviderSettings(
            label=agent["label"],
            type=agent["provider_type"],
            model=agent["model"],
            base_url="" if agent["provider_type"] == "dashscope" else agent["base_url"],
            api_key=agent["api_key"],
            temperature=0,
            timeout_seconds=min(int(agent["timeout_seconds"]), 15),
            max_retries=0,
        )
        test_settings.agent.providers = {provider_key: provider}
        test_settings.agent.provider = provider_key

        llm = build_chat_model(test_settings)
        result = await llm.ainvoke(AGENT_TEST_PROMPT)
        trace_id = str(uuid4())
        update_agent_test_status(database_path, provider_key, "success", trace_id)
        tokens = _extract_usage_metadata(result)
        if tokens["total_tokens"] > 0:
            from app.db.token_usage_store import record_token_usage
            record_token_usage(
                database_path,
                provider_key=provider_key,
                provider_type=agent["provider_type"],
                model=agent["model"],
                call_type="test",
                trace_id=trace_id,
                input_tokens=tokens["input_tokens"],
                output_tokens=tokens["output_tokens"],
                total_tokens=tokens["total_tokens"],
            )
        return {"ok": True, "result": _extract_message_content(result) or str(result)}
    except Exception as exc:
        trace_id = str(uuid4())
        update_agent_test_status(database_path, provider_key, "failed", trace_id)
        error_info = _extract_connectivity_test_error(exc, request_info)
        raise ApiError(
            "Agent 连通性测试失败",
            status_code=400,
            trace_id=trace_id,
            log_message=f"Agent test failed: {provider_key}",
            log_detail=error_info,
            log_category="ai",
        ) from None
