"""BotService reload 编排单测。

覆盖：
- CRUD 落库后调用 Gateway /api/v1/admin/reload，header X-Internal-Token 正确。
- reload 失败（网络异常 / 4xx / 5xx）不抛异常，CRUD 返回值不受影响。
- INTERNAL_ADMIN_TOKEN 未配置时跳过 reload（不发请求）。
- list_bots 不触发 reload。
- gateway_url 末尾斜杠被剥离。
- data_client 落库抛异常时 reload 不被触发（异常向上抛，不吞）。
"""

from __future__ import annotations

from typing import Any

from tests.conftest import (
    FakeDataClient,
    FakeHttpPost,
    _make_bot_service,
)

_VALID_CREATE_KWARGS: dict[str, str] = {
    "bot_id": "bot-1",
    "name": "飞书机器人",
    "platform": "feishu",
    "app_id": "cli_xxx",
    "app_secret": "secret",
    "mode": "test",
}


# ── create ──────────────────────────────────


def test_create_bot_triggers_reload_with_internal_token(
    bot_service, fake_data_client: FakeDataClient, fake_http_post: FakeHttpPost
) -> None:
    """create 落库成功后应经 X-Internal-Token 头触发 Gateway reload。"""
    result = bot_service.create_bot(**_VALID_CREATE_KWARGS)

    assert result == fake_data_client.create_result
    assert fake_data_client.calls[-1][0] == "create_bot"
    assert len(fake_http_post.calls) == 1
    url, headers, timeout = fake_http_post.calls[0]
    assert url == "http://127.0.0.1:8864/api/v1/admin/reload"
    assert headers == {"X-Internal-Token": "test-internal-token"}
    assert timeout == 5.0


def test_create_bot_reload_network_error_does_not_raise(
    fake_data_client: FakeDataClient, failing_http_post: FakeHttpPost
) -> None:
    """reload 网络异常时不应抛出，CRUD 结果正常返回。"""
    service = _make_bot_service(fake_data_client, failing_http_post)
    result = service.create_bot(**_VALID_CREATE_KWARGS)
    assert result == fake_data_client.create_result
    assert len(failing_http_post.calls) == 1


def test_create_bot_reload_timeout_does_not_raise(
    fake_data_client: FakeDataClient, timeout_http_post: FakeHttpPost
) -> None:
    """reload 超时异常不应抛出。"""
    service = _make_bot_service(fake_data_client, timeout_http_post)
    result = service.create_bot(**_VALID_CREATE_KWARGS)
    assert result == fake_data_client.create_result


def test_create_bot_reload_4xx_does_not_raise(
    fake_data_client: FakeDataClient, unauthorized_http_post: FakeHttpPost
) -> None:
    """reload 返回 401（令牌不匹配）不应抛出。"""
    service = _make_bot_service(fake_data_client, unauthorized_http_post)
    result = service.create_bot(**_VALID_CREATE_KWARGS)
    assert result == fake_data_client.create_result


def test_create_bot_reload_5xx_does_not_raise(
    fake_data_client: FakeDataClient, server_error_http_post: FakeHttpPost
) -> None:
    """reload 返回 500 不应抛出。"""
    service = _make_bot_service(fake_data_client, server_error_http_post)
    result = service.create_bot(**_VALID_CREATE_KWARGS)
    assert result == fake_data_client.create_result


# ── update / delete ──────────────────────────────────


def test_update_bot_triggers_reload(
    bot_service, fake_data_client: FakeDataClient, fake_http_post: FakeHttpPost
) -> None:
    """update 落库成功后应触发 reload。"""
    result = bot_service.update_bot(bot_id="bot-1", name="new-name")

    assert result == fake_data_client.update_result
    assert fake_data_client.calls[-1][0] == "update_bot"
    assert len(fake_http_post.calls) == 1
    url, _headers, _timeout = fake_http_post.calls[0]
    assert url.endswith("/api/v1/admin/reload")


def test_delete_bot_triggers_reload(
    bot_service, fake_data_client: FakeDataClient, fake_http_post: FakeHttpPost
) -> None:
    """delete 落库成功后应触发 reload。"""
    result = bot_service.delete_bot(bot_id="bot-1")

    assert result == fake_data_client.delete_result
    assert fake_data_client.calls[-1][0] == "delete_bot"
    assert len(fake_http_post.calls) == 1


def test_update_bot_reload_failure_does_not_raise(
    fake_data_client: FakeDataClient, timeout_http_post: FakeHttpPost
) -> None:
    """update 后 reload 异常不应抛出。"""
    service = _make_bot_service(fake_data_client, timeout_http_post)
    result = service.update_bot(bot_id="bot-1", name="n")
    assert result == fake_data_client.update_result


def test_delete_bot_reload_failure_does_not_raise(
    fake_data_client: FakeDataClient, failing_http_post: FakeHttpPost
) -> None:
    """delete 后 reload 异常不应抛出。"""
    service = _make_bot_service(fake_data_client, failing_http_post)
    result = service.delete_bot(bot_id="bot-1")
    assert result == fake_data_client.delete_result


# ── list ──────────────────────────────────


def test_list_bots_does_not_trigger_reload(
    bot_service, fake_data_client: FakeDataClient, fake_http_post: FakeHttpPost
) -> None:
    """list_bots 是只读查询，不应触发 reload。"""
    result = bot_service.list_bots(page=1, page_size=20)

    assert result == fake_data_client.list_result
    assert fake_data_client.calls == [
        ("list_bots", {"page": 1, "page_size": 20, "created_by": None})
    ]
    assert fake_http_post.calls == []


# ── INTERNAL_ADMIN_TOKEN 未配置 ──────────────────────────────────


def test_reload_skipped_when_token_empty_create(
    bot_service_no_token, fake_data_client: FakeDataClient, fake_http_post: FakeHttpPost
) -> None:
    """INTERNAL_ADMIN_TOKEN 留空时 create 跳过 reload，不发任何 HTTP 请求。"""
    result = bot_service_no_token.create_bot(**_VALID_CREATE_KWARGS)
    assert result == fake_data_client.create_result
    assert fake_http_post.calls == []


def test_reload_skipped_when_token_empty_update(
    bot_service_no_token, fake_data_client: FakeDataClient, fake_http_post: FakeHttpPost
) -> None:
    """update 在 token 空时也跳过 reload。"""
    bot_service_no_token.update_bot(bot_id="bot-1", name="n")
    assert fake_http_post.calls == []


def test_reload_skipped_when_token_empty_delete(
    bot_service_no_token, fake_data_client: FakeDataClient, fake_http_post: FakeHttpPost
) -> None:
    """delete 在 token 空时也跳过 reload。"""
    bot_service_no_token.delete_bot(bot_id="bot-1")
    assert fake_http_post.calls == []


# ── gateway_url 规范化 ──────────────────────────────────


def test_gateway_url_trailing_slash_stripped(fake_data_client: FakeDataClient) -> None:
    """gateway_url 末尾斜杠应被剥离，避免拼接出 //api/v1/admin/reload。"""
    post = FakeHttpPost()
    service = _make_bot_service(
        fake_data_client, post, gateway_url="http://127.0.0.1:8864/"
    )
    service.create_bot(**_VALID_CREATE_KWARGS)
    url, _headers, _timeout = post.calls[0]
    assert url == "http://127.0.0.1:8864/api/v1/admin/reload"


# ── reload 时机 ──────────────────────────────────


def test_reload_called_after_data_persisted(
    bot_service, fake_data_client: FakeDataClient, fake_http_post: FakeHttpPost
) -> None:
    """reload 必须在 data_client 落库成功后才触发。"""
    bot_service.create_bot(**_VALID_CREATE_KWARGS)
    assert len(fake_data_client.calls) == 1
    assert len(fake_http_post.calls) == 1


def test_reload_not_called_when_data_client_raises(
    fake_data_client: FakeDataClient, fake_http_post: FakeHttpPost
) -> None:
    """data_client 落库抛异常时 reload 不应被触发（异常向上抛，不吞）。"""
    service = _make_bot_service(fake_data_client, fake_http_post)

    def raise_create(**_payload: Any) -> dict[str, Any]:
        raise RuntimeError("db down")

    fake_data_client.create_bot = raise_create  # type: ignore[method-assign]

    raised = False
    try:
        service.create_bot(**_VALID_CREATE_KWARGS)
    except RuntimeError:
        raised = True
    assert raised
    assert fake_http_post.calls == []


# ── reload URL 与 header 完整性 ──────────────────────────────────


def test_reload_uses_correct_url_and_header(
    bot_service, fake_http_post: FakeHttpPost
) -> None:
    """reload 请求 URL 与 header 完整正确。"""
    bot_service.update_bot(bot_id="bot-1", mode="prod")
    assert len(fake_http_post.calls) == 1
    url, headers, _timeout = fake_http_post.calls[0]
    assert url == "http://127.0.0.1:8864/api/v1/admin/reload"
    assert "X-Internal-Token" in headers
    assert headers["X-Internal-Token"] == "test-internal-token"


def test_reload_success_logs_info(bot_service, fake_http_post: FakeHttpPost) -> None:
    """reload 2xx 成功应记录 info 日志（此处仅验证不抛异常、调用发生）。"""
    bot_service.delete_bot(bot_id="bot-1")
    assert len(fake_http_post.calls) == 1
