"""Agent HTTP 健康检查测试。"""

from __future__ import annotations

from typing import Any

from fastapi import Query
from fastapi.testclient import TestClient
from observability import TraceBatch

from app.core.config import Settings
from app.core.runtime import RuntimeManager, RuntimeStatus
from app.main import create_app


async def _discard_trace(_batch: TraceBatch) -> None:
    """测试期间丢弃 Trace。"""


def _test_settings(*, app_env: str = "test") -> Settings:
    """构造不读取本地文件的测试配置。"""
    return Settings(_env_file=None, app_env=app_env)


def test_health_returns_success_envelope() -> None:
    """存活检查应返回统一成功信封。"""
    application = create_app(
        configured_settings=_test_settings(),
        trace_sink=_discard_trace,
    )
    with TestClient(application) as client:
        response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {
        "success": True,
        "message": "ok",
        "data": {"status": "healthy"},
    }


def test_readiness_reports_runtime_status() -> None:
    """就绪检查应返回 Runtime 状态。"""
    runtime = RuntimeManager()
    application = create_app(
        configured_settings=_test_settings(),
        runtime=runtime,
        trace_sink=_discard_trace,
    )
    with TestClient(application) as client:
        response = client.get("/api/v1/health/ready")
        assert runtime.status is RuntimeStatus.READY
    assert response.status_code == 200
    assert response.json()["data"]["runtime_status"] == "ready"
    assert runtime.status is RuntimeStatus.STOPPED


def test_root_returns_service_information() -> None:
    """根路径应返回 Agent 服务信息。"""
    application = create_app(
        configured_settings=_test_settings(),
        trace_sink=_discard_trace,
    )
    with TestClient(application) as client:
        response = client.get("/")
    assert response.status_code == 200
    assert response.json()["data"]["name"] == "Digital Employee Agent"


def test_not_found_uses_error_envelope() -> None:
    """不存在的路径应返回统一错误信封。"""
    application = create_app(
        configured_settings=_test_settings(),
        trace_sink=_discard_trace,
    )
    with TestClient(application) as client:
        response = client.get("/missing")
    assert response.status_code == 404
    assert response.json()["data"]["code"] == "HTTP_404"


def test_validation_error_uses_error_envelope() -> None:
    """请求参数校验失败应返回统一错误信封。"""
    application = create_app(
        configured_settings=_test_settings(),
        trace_sink=_discard_trace,
    )

    @application.get("/test-validation")
    def validation_route(value: int = Query(...)) -> dict[str, Any]:
        return {"value": value}

    with TestClient(application) as client:
        response = client.get("/test-validation", params={"value": "invalid"})
    assert response.status_code == 422
    assert response.json()["data"]["code"] == "VALIDATION_FAILED"


def test_production_disables_openapi() -> None:
    """生产环境应关闭 OpenAPI 文档。"""
    application = create_app(
        configured_settings=_test_settings(app_env="production"),
        trace_sink=_discard_trace,
    )
    assert application.docs_url is None
    assert application.redoc_url is None
    assert application.openapi_url is None
