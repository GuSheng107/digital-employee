from fastapi import APIRouter, Depends

from app.api.deps import verify_api_key
from app.api.routes import cache, data_items, health, storage, system_config


api_router = APIRouter()
# 基础健康检查端点对外豁免，便于 K8s/负载均衡探活；
# /health/dependencies 在端点级别单独挂载 API Key 认证。
api_router.include_router(health.router, prefix="/health", tags=["health"])
# 业务端点统一挂载 API Key 认证依赖。
api_router.include_router(
    system_config.router,
    prefix="/system",
    tags=["system-config"],
    dependencies=[Depends(verify_api_key)],
)
api_router.include_router(
    data_items.router,
    prefix="/data-items",
    tags=["data-items"],
    dependencies=[Depends(verify_api_key)],
)
api_router.include_router(
    storage.router,
    prefix="/storage",
    tags=["storage"],
    dependencies=[Depends(verify_api_key)],
)
api_router.include_router(
    cache.router,
    prefix="/cache",
    tags=["cache"],
    dependencies=[Depends(verify_api_key)],
)
