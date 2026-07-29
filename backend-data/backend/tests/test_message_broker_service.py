"""backend-data 消息基础设施服务测试。"""

from __future__ import annotations

import asyncio
from typing import Any

import pytest
from api_common import ValidationError

from app.services.message_broker_service import MessageBrokerService


class _FakeRedis:
    def __init__(self) -> None:
        self.claimed: dict[str, Any] | None = None
        self.acked: str | None = None
        self.rejected: str | None = None

    def claim_relay_message(self, **_kwargs: Any) -> dict[str, Any] | None:
        return self.claimed

    def ack_relay_message(self, *, receipt_id: str, **_kwargs: Any) -> bool:
        self.acked = receipt_id
        return True

    def nack_relay_message(self, *, receipt_id: str, **_kwargs: Any) -> bool:
        self.rejected = receipt_id
        return True


class _FakeExchange:
    def __init__(self) -> None:
        self.routing_key: str | None = None
        self.body: bytes | None = None

    async def publish(self, message: Any, *, routing_key: str) -> None:
        self.routing_key = routing_key
        self.body = message.body


def test_claim_uses_redis_relay_before_touching_mq() -> None:
    fake_redis = _FakeRedis()
    fake_redis.claimed = {
        "receipt_id": "receipt-1",
        "payload": "{}",
    }
    service = MessageBrokerService(fake_redis)  # type: ignore[arg-type]

    result = asyncio.run(service.claim_outbound(timeout_seconds=0.1))

    assert result == fake_redis.claimed


def test_publish_builds_routing_key_inside_backend_data(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    fake_redis = _FakeRedis()
    exchange = _FakeExchange()
    service = MessageBrokerService(fake_redis)  # type: ignore[arg-type]
    service._exchange = exchange  # noqa: SLF001

    async def _ready() -> dict[str, bool]:
        return {"connected": True}

    monkeypatch.setattr(service, "ensure_topology", _ready)

    result = asyncio.run(
        service.publish_inbound(
            platform="wechat",
            bot_id="bot_1",
            payload='{"ok":true}',
        )
    )

    assert result["routing_key"].endswith(".wechat.bot_1")
    assert exchange.routing_key == result["routing_key"]
    assert exchange.body == b'{"ok":true}'


@pytest.mark.parametrize("invalid_value", ["bad.value", "含中文", ""])
def test_publish_rejects_unsafe_routing_segments(
    invalid_value: str,
) -> None:
    service = MessageBrokerService(_FakeRedis())  # type: ignore[arg-type]

    with pytest.raises(ValidationError):
        asyncio.run(
            service.publish_inbound(
                platform=invalid_value,
                bot_id="bot_1",
                payload="{}",
            )
        )


def test_ack_and_nack_are_delegated_to_redis_lease() -> None:
    fake_redis = _FakeRedis()
    service = MessageBrokerService(fake_redis)  # type: ignore[arg-type]

    service.ack_outbound("receipt-1")
    service.nack_outbound("receipt-2")

    assert fake_redis.acked == "receipt-1"
    assert fake_redis.rejected == "receipt-2"
