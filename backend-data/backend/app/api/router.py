from auth_utils import PermissionCode
from fastapi import APIRouter, Depends

from app.api.deps import require_service_or_permission, verify_api_key
from app.api.routes import (
    cache,
    data_items,
    health,
    identity,
    infrastructure,
    observability,
    storage,
    system_config,
)
from app.core.storage_constants import STORAGE_ROUTE_PREFIX


api_router = APIRouter()
# 基础健康检查端点对外豁免，便于 K8s/负载均衡探活；
# /health/dependencies 在端点级别单独挂载 API Key 认证。
api_router.include_router(health.router, prefix="/health", tags=["health"])
# 头像读取供浏览器 img 标签使用，只开放 avatars/ 前缀；上传仍受 API Key 保护。
api_router.include_router(
    storage.public_router,
    prefix=STORAGE_ROUTE_PREFIX,
    tags=["storage"],
)
# 业务端点统一挂载 API Key 认证依赖。
api_router.include_router(
    system_config.router,
    prefix="/system",
    tags=["system-config"],
    dependencies=[
        Depends(require_service_or_permission(PermissionCode.DATA_PLATFORM_CONFIG))
    ],
)
api_router.include_router(
    data_items.router,
    prefix="/data-items",
    tags=["data-items"],
    dependencies=[
        Depends(require_service_or_permission(PermissionCode.DATA_PLATFORM_DATA_ITEMS))
    ],
)
api_router.include_router(
    storage.router,
    prefix=STORAGE_ROUTE_PREFIX,
    tags=["storage"],
    dependencies=[
        Depends(require_service_or_permission(PermissionCode.DATA_PLATFORM_CONFIG))
    ],
)
api_router.include_router(
    cache.router,
    prefix="/cache",
    tags=["cache"],
    dependencies=[
        Depends(require_service_or_permission(PermissionCode.DATA_PLATFORM_CONFIG))
    ],
)
api_router.include_router(
    identity.router,
    prefix="/identity",
    tags=["identity-internal"],
    dependencies=[Depends(verify_api_key)],
)
api_router.include_router(
    observability.router,
    prefix="/observability",
    tags=["observability"],
)
api_router.include_router(
    infrastructure.router,
    prefix="/infrastructure",
    tags=["infrastructure-internal"],
    dependencies=[Depends(verify_api_key)],
)
