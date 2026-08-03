from api_common import ApiResponse, success_response
from auth_utils import PermissionCode
from fastapi import APIRouter, Depends

from app.api.deps import require_service_or_permission
from app.services.health_service import HealthService

router = APIRouter()


@router.get("", response_model=ApiResponse)
def api_health() -> dict:
    return success_response({"status": "healthy"})


# /ready 返回核心依赖探活详情（无认证），供 start-all.py 启动后验收。
# 与 /dependencies 不同，/ready 不要求 API Key 或 Dashboard 权限，
# 仅检查核心依赖（DB、Redis、MinIO）的连通性，不暴露敏感细节。
@router.get("/ready", response_model=ApiResponse)
def api_ready() -> dict:
    statuses = HealthService().test_dependencies()
    return success_response(statuses.model_dump())


# /dependencies 返回依赖探活详情（失败时可能携带异常消息），
# 单独要求服务 API Key 或 Dashboard 权限；基础 /health 仍豁免以支持探活。
@router.get(
    "/dependencies",
    response_model=ApiResponse,
    dependencies=[
        Depends(
            require_service_or_permission(
                PermissionCode.DATA_PLATFORM_DASHBOARD
            )
        )
    ],
)
def dependencies() -> dict:
    statuses = HealthService().test_dependencies()
    return success_response(statuses.model_dump())
