from fastapi import APIRouter

from app.api.routes import cache, data_items, ddl, health, storage, system_config


api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(
    system_config.router,
    prefix="/system",
    tags=["system-config"],
)
api_router.include_router(data_items.router, prefix="/data-items", tags=["data-items"])
api_router.include_router(storage.router, prefix="/storage", tags=["storage"])
api_router.include_router(cache.router, prefix="/cache", tags=["cache"])
api_router.include_router(ddl.router, prefix="/ddl", tags=["ddl"])
