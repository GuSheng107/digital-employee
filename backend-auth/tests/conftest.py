"""backend-auth bot_service 单测共享 fixture。

测试不依赖真实 backend-data / Gateway / Nacos：通过注入 fake DataClient
与 fake http_post 替身，校验 BotService 的 reload 编排逻辑。
"""

from __future__ import annotations

import os

# 必须在任何 app.* import 之前设置环境变量。
# NACOS_SERVER_ADDR 留空跳过 Nacos 拉取；API_KEY 留空不影响 BotService 单测
# （BotService 不走 verify_api_key 依赖）。
os.environ.setdefault("NACOS_SERVER_ADDR", "")
os.environ.setdefault("API_KEY", "test-api-key")
os.environ.setdefault("INTERNAL_ADMIN_TOKEN", "test-internal-token")
os.environ.setdefault("GATEWAY_BASE_URL", "http://127.0.0.1:8864")

from typing import Any

import pytest


class FakeDataClient:
    """记录调用参数并返回预设结果的假 DataClient。"""

    def __init__(self) -> None:
        self.calls: list[tuple[str, dict[str, Any]]] = []
        self.list_result: dict[str, Any] = {"items": [], "total": 0, "page": 1, "page_size": 20}
        self.create_result: dict[str, Any] = {"bot_id": "bot-1", "status": "created"}
        self.update_result: dict[str, Any] = {"bot_id": "bot-1", "status": "updated"}
        self.delete_result: dict[str, Any] = {"bot_id": "bot-1", "status": "deleted"}

    def list_bots(
        self, *, page: int, page_size: int, created_by: int | None = None
    ) -> dict[str, Any]:
        self.calls.append(
            ("list_bots", {"page": page, "page_size": page_size, "created_by": created_by})
        )
        return self.list_result

    def create_bot(self, **payload: Any) -> dict[str, Any]:
        self.calls.append(("create_bot", payload))
        return self.create_result

    def update_bot(self, *, bot_id: str, **fields: Any) -> dict[str, Any]:
        self.calls.append(("update_bot", {"bot_id": bot_id, **fields}))
        return self.update_result

    def delete_bot(self, bot_id: str) -> dict[str, Any]:
        self.calls.append(("delete_bot", {"bot_id": bot_id}))
        return self.delete_result

    def create_user(self, **payload: Any) -> dict[str, Any]:
        self.calls.append(("create_user", payload))
        return {"user_id": 1, "status": "created"}

    def assign_user_roles(self, *, user_id: int, role_codes: list[str], **kwargs: Any) -> dict[str, Any]:
        self.calls.append(("assign_user_roles", {"user_id": user_id, "role_codes": role_codes}))
        return {"user_id": user_id, "status": "assigned"}


class FakeResponse:
    """httpx 响应替身。"""

    def __init__(self, status_code: int = 200, text: str = "") -> None:
        self.status_code = status_code
        self.text = text


class FakeHttpPost:
    """记录调用并返回预设响应的假 httpx.post。"""

    def __init__(self, response: FakeResponse | None = None, exc: Exception | None = None) -> None:
        self.calls: list[tuple[str, dict[str, str], float]] = []
        self._response = response or FakeResponse(status_code=200, text='{"success":true}')
        self._exc = exc

    def __call__(
        self,
        url: str,
        *,
        headers: dict[str, str],
        timeout: float,
    ) -> Any:
        self.calls.append((url, dict(headers), timeout))
        if self._exc is not None:
            raise self._exc
        return self._response


@pytest.fixture
def fake_data_client() -> FakeDataClient:
    """返回记录调用的假 DataClient。"""
    return FakeDataClient()


@pytest.fixture
def fake_http_post() -> FakeHttpPost:
    """返回记录调用的假 httpx.post（默认 200 成功）。"""
    return FakeHttpPost()


@pytest.fixture
def failing_http_post() -> FakeHttpPost:
    """返回始终抛 ConnectionError 的假 httpx.post（模拟网络错误）。"""
    return FakeHttpPost(exc=ConnectionError("gateway unreachable"))


@pytest.fixture
def timeout_http_post() -> FakeHttpPost:
    """返回始终抛 TimeoutError 的假 httpx.post。"""
    return FakeHttpPost(exc=TimeoutError("request timed out"))


@pytest.fixture
def unauthorized_http_post() -> FakeHttpPost:
    """返回 401 的假 httpx.post（令牌不匹配）。"""
    return FakeHttpPost(response=FakeResponse(status_code=401, text="unauthorized"))


@pytest.fixture
def server_error_http_post() -> FakeHttpPost:
    """返回 500 的假 httpx.post。"""
    return FakeHttpPost(response=FakeResponse(status_code=500, text="internal error"))


def _make_bot_service(
    data_client: FakeDataClient,
    http_post: FakeHttpPost,
    *,
    internal_token: str = "test-internal-token",
    gateway_url: str = "http://127.0.0.1:8864",
):
    """构造绑定 fake 依赖的 BotService。"""
    from app.services.bot_service import BotService

    return BotService(
        data_client,
        gateway_url=gateway_url,
        internal_token=internal_token,
        http_post=http_post,
    )


@pytest.fixture
def bot_service(fake_data_client: FakeDataClient, fake_http_post: FakeHttpPost):
    """返回注入了 fake 依赖的 BotService（200 成功 reload）。"""
    return _make_bot_service(fake_data_client, fake_http_post)


@pytest.fixture
def bot_service_no_token(fake_data_client: FakeDataClient, fake_http_post: FakeHttpPost):
    """返回未配置 INTERNAL_ADMIN_TOKEN 的 BotService（应跳过 reload）。"""
    return _make_bot_service(fake_data_client, fake_http_post, internal_token="")
