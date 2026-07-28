from auth_utils import PermissionCode
from fastapi import APIRouter, Depends

from app.api.deps import require_service_or_permission
from app.schemas.common import ApiResponse
from app.services.health_service import HealthService
from app.utils.response import success_response


router = APIRouter()


@router.get("", response_model=ApiResponse)
def api_health() -> dict:
    return success_response({"status": "healthy"})


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
