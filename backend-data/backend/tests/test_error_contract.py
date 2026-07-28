"""统一错误码响应契约测试。"""

from fastapi.testclient import TestClient

from app.main import app


def test_http_error_response_contains_code_and_message() -> None:
    """实际 HTTP 错误响应必须同时包含错误码与错误信息。"""
    response = TestClient(app).get("/route-that-does-not-exist")

    assert response.status_code == 404
    body = response.json()
    assert body["message"] == "Not Found"
    assert body["data"]["code"] == "HTTP_404"
