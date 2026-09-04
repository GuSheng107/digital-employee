"""Agent 健康检查 Schema。"""

from pydantic import BaseModel

from app.core.runtime import RuntimeStatus


class ServiceInfo(BaseModel):
    """服务基本信息。"""

    name: str
    version: str
    environment: str
    status: str


class ReadinessInfo(BaseModel):
    """服务就绪信息。"""

    status: str
    runtime_status: RuntimeStatus
