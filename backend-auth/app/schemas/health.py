"""健康检查相关 schema。"""

from __future__ import annotations

from pydantic import BaseModel


class ServiceInfo(BaseModel):
    """服务基本信息。"""

    name: str
    version: str
    environment: str
    status: str


class DependencyStatus(BaseModel):
    """单个依赖的探活状态。"""

    ok: bool
    message: str = "ok"
    latency_ms: float | None = None


class DependenciesStatus(BaseModel):
    """所有依赖的探活状态汇总。"""

    core_db: DependencyStatus
    redis: DependencyStatus
