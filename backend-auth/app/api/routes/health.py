"""健康检查路由。

基础 /health 端点对外豁免，便于 K8s/负载均衡探活；
/health/dependencies 返回依赖探活详情，单独挂载 API Key 认证。
"""

from __future__ import annotations

from api_common import ApiResponse, success_response
from fastapi import APIRouter, Depends

from app.api.deps import verify_api_key
from app.schemas.health import ServiceInfo
from app.services.health_service import HealthService

router = APIRouter()


@router.get("", response_model=ApiResponse)
def api_health() -> dict:
    """基础健康检查端点。"""
    return success_response({"status": "healthy"})


@router.get(
    "/dependencies",
    response_model=ApiResponse,
    dependencies=[Depends(verify_api_key)],
)
def dependencies() -> dict:
    """依赖探活详情端点，需要 API Key。"""
    statuses = HealthService().test_dependencies()
    return success_response(statuses.model_dump())


@router.get("/info", response_model=ApiResponse)
def service_info() -> dict:
    """返回服务基本信息（名称、版本、环境）。"""
    from app.core.config import settings

    return success_response(
        ServiceInfo(
            name=settings.app_name,
            version=settings.app_version,
            environment=settings.app_env,
            status="running",
        ).model_dump()
    )
