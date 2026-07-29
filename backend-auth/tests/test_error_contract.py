"""认证服务错误响应契约测试。"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_validation_error_contains_code_and_specific_message() -> None:
    """自定义字段校验失败不得退化为不可序列化的 500。"""
    response = TestClient(app).post(
        "/api/v1/auth/register",
        json={
            "username": "tester",
            "password": "too-short",
            "email": "invalid-email",
            "phone": "123",
            "invite_code": "A",
        },
    )

    assert response.status_code == 422
    body = response.json()
    assert body["data"]["code"] == "VALIDATION_FAILED"
    assert body["message"].startswith("请求参数校验失败：")
    assert isinstance(body["data"]["detail"], list)
