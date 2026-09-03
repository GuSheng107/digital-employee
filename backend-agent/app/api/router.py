"""Agent API 路由聚合。"""

from fastapi import APIRouter

from app.api.routes import agents, health

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(agents.router, tags=["agents"])
