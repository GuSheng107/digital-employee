"""API 路由聚合。

健康检查端点对外豁免以便 K8s/负载均衡探活；认证端点不挂载 API Key，
但 /auth/me 等需要登录态的端点通过 access_token 鉴权。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import auth, health

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
