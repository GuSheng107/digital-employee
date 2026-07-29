"""网关 share/data-client 适配层测试。"""

from __future__ import annotations

import asyncio
from io import BytesIO
from typing import Any

from src.utils.data_access import (
    GatewayMessageBusClient,
    GatewayStorageClient,
)


class _FakeDataClient:
    def __init__(self) -> None:
        self.upload: dict[str, Any] | None = None
        self.published: dict[str, str] | None = None
        self.closed = False

    def upload_object(self, **kwargs: Any) -> dict[str, str]:
        self.upload = kwargs
        return {"file_url": "http://storage.invalid/bucket/object"}

    def download_object_by_url(self, file_url: str) -> tuple[bytes, str]:
        assert file_url == "http://storage.invalid/bucket/object"
        return b"content", "image/png"

    async def ensure_message_broker(self) -> dict[str, bool]:
        return {"connected": True}

    async def publish_inbound_message(
        self,
        **kwargs: str,
    ) -> dict[str, str]:
        self.published = kwargs
        return {"message_id": "message-1"}

    async def claim_outbound_message(
        self,
        *,
        timeout_seconds: float,
    ) -> dict[str, str]:
        assert timeout_seconds > 0
        return {"receipt_id": "receipt-1", "payload": "{}"}

    async def acknowledge_outbound_message(
        self,
        receipt_id: str,
    ) -> dict[str, str]:
        return {"receipt_id": receipt_id}

    async def reject_outbound_message(
        self,
        receipt_id: str,
    ) -> dict[str, str]:
        return {"receipt_id": receipt_id}

    async def aclose(self) -> None:
        self.closed = True


def test_storage_operations_delegate_to_data_client() -> None:
    fake = _FakeDataClient()
    client = GatewayStorageClient(fake)  # type: ignore[arg-type]

    file_url = client.upload_file(
        object_name="wechat/bot/image.png",
        data=BytesIO(b"content"),
        length=7,
        content_type="image/png",
    )
    downloaded = client.download_file(file_url=file_url)

    assert fake.upload is not None
    assert fake.upload["object_name"] == "wechat/bot/image.png"
    assert downloaded.read() == b"content"


def test_message_operations_delegate_to_data_client() -> None:
    fake = _FakeDataClient()
    client = GatewayMessageBusClient(fake)  # type: ignore[arg-type]

    async def _exercise() -> None:
        status = await client.ensure_ready()
        await client.publish(
            platform="wechat",
            bot_id="bot_1",
            payload="{}",
        )
        claimed = await client.claim()
        assert claimed is not None
        await client.acknowledge(claimed["receipt_id"])
        await client.reject(claimed["receipt_id"])
        await client.close()
        assert status["connected"] is True

    asyncio.run(_exercise())
    assert fake.published == {
        "platform": "wechat",
        "bot_id": "bot_1",
        "payload": "{}",
    }
    assert fake.closed is True
