from pydantic import BaseModel


class ServiceInfo(BaseModel):
    name: str
    version: str
    environment: str
    status: str


class DependencyStatus(BaseModel):
    ok: bool
    message: str = "ok"
    latency_ms: float | None = None


class DependenciesStatus(BaseModel):
    core_db: DependencyStatus
    vector_db: DependencyStatus
    redis: DependencyStatus
    minio: DependencyStatus
