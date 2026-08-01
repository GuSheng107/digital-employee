"""API 路由聚合。

健康检查端点对外豁免以便 K8s/负载均衡探活；认证端点不挂载 API Key，
但 /auth/me 等需要登录态的端点通过 access_token 鉴权。
"""

from __future__ import annotations

from fastapi import APIRouter

from app.api.routes import (
    agents,
    auth,
    bots,
    health,
    invite_codes,
    menus,
    permissions,
    roles,
    users,
)

api_router = APIRouter()
api_router.include_router(health.router, prefix="/health", tags=["health"])
api_router.include_router(auth.router, prefix="/auth", tags=["auth"])
api_router.include_router(invite_codes.router, prefix="/invite-codes", tags=["invite-codes"])
api_router.include_router(users.router, prefix="/users", tags=["users"])
api_router.include_router(roles.router, prefix="/roles", tags=["roles"])
api_router.include_router(menus.router, prefix="/menus", tags=["menus"])
api_router.include_router(
    permissions.router,
    prefix="/permissions",
    tags=["permissions"],
)
api_router.include_router(bots.router, prefix="/bots", tags=["bots"])
api_router.include_router(agents.router, prefix="/agents", tags=["agents"])
