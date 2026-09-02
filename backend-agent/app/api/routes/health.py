"""Agent 服务健康检查路由。"""

from __future__ import annotations

from typing import Any, cast

from api_common import ApiResponse, ServiceUnavailableError, success_response
from fastapi import APIRouter, Request

from app.core.config import Settings
from app.core.runtime import RuntimeManager
from app.schemas.health import ReadinessInfo, ServiceInfo

router = APIRouter()


def _get_runtime(request: Request) -> RuntimeManager:
    """从应用状态中读取 RuntimeManager。

    Args:
        request: 当前 FastAPI 请求。

    Returns:
        已初始化的 RuntimeManager。

    Raises:
        ServiceUnavailableError: 生命周期尚未完成初始化。
    """
    runtime = getattr(request.app.state, "runtime", None)
    if not isinstance(runtime, RuntimeManager):
        raise ServiceUnavailableError(message="Agent 运行时尚未初始化")
    return runtime


@router.get("", response_model=ApiResponse)
def health() -> dict[str, Any]:
    """返回进程存活状态。"""
    return cast(dict[str, Any], success_response({"status": "healthy"}))


@router.get("/ready", response_model=ApiResponse)
def readiness(request: Request) -> dict[str, Any]:
    """返回服务就绪状态。"""
    runtime = _get_runtime(request)
    if not runtime.is_ready:
        raise ServiceUnavailableError(message="Agent 服务尚未就绪")
    return cast(
        dict[str, Any],
        success_response(
            ReadinessInfo(
                status="ready",
                runtime_status=runtime.status,
            ).model_dump(mode="json")
        ),
    )


@router.get("/info", response_model=ApiResponse)
def service_info(request: Request) -> dict[str, Any]:
    """返回非敏感服务信息。"""
    configured_settings = cast(Settings, request.app.state.settings)
    return cast(
        dict[str, Any],
        success_response(
            ServiceInfo(
                name=configured_settings.app_name,
                version=configured_settings.app_version,
                environment=configured_settings.app_env,
                status="running",
            ).model_dump()
        ),
    )
