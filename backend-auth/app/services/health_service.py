"""认证服务依赖健康检查代理。"""

from __future__ import annotations

from data_client import DataClient, get_data_client

from app.core.config import ConnectionTarget
from app.schemas.health import DependenciesStatus


class HealthService:
    """通过 backend-data 执行基础设施探活。"""

    def __init__(self, data_client: DataClient | None = None) -> None:
        self._data = data_client or get_data_client()

    def test_dependencies(
        self,
        target: ConnectionTarget = "all",
    ) -> DependenciesStatus:
        """获取 backend-data 返回的 PostgreSQL/Redis 状态。"""
        payload = self._data.test_dependencies(target=target)
        return DependenciesStatus.model_validate(payload)
