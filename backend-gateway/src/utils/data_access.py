"""网关访问 backend-data 的唯一共享客户端适配层。

本模块只依赖 ``backend-share/data-client``。网关不持有 PostgreSQL、
Redis、MinIO 或 RabbitMQ 的驱动、连接、拓扑和凭证。
"""

from __future__ import annotations

import os
from io import BytesIO
from typing import Any

from data_client import DataClient, get_data_client


DEFAULT_MESSAGE_POLL_SECONDS = 20.0
DEFAULT_DATA_RETRY_SECONDS = 5.0


def _read_positive_float(name: str, default: float) -> float:
    raw_value = os.environ.get(name)
    if raw_value is None:
        return default
    try:
        value = float(raw_value)
    except ValueError:
        return default
    return value if value > 0 else default


class GatewayStorageClient:
    """保持适配器所需流接口，同时把对象存储执行委托给 backend-data。"""

    def __init__(self, data_client: DataClient | None = None) -> None:
        self._data = data_client

    def upload_file(
        self,
        *,
        object_name: str,
        data: BytesIO,
        length: int,
        content_type: str = "application/octet-stream",
    ) -> str:
        """通过 data-client 上传业务对象并返回存储 URL。"""
        data.seek(0)
        content = data.read()
        if len(content) != length:
            length = len(content)
        result = self._get_data_client().upload_object(
            object_name=object_name,
            filename=object_name.rsplit("/", 1)[-1],
            data=content[:length],
            content_type=content_type,
        )
        file_url = result.get("file_url")
        if not isinstance(file_url, str) or not file_url:
            raise RuntimeError("backend-data 未返回有效文件地址")
        return file_url

    def download_file(self, *, file_url: str) -> BytesIO:
        """通过 data-client 解析受信存储 URL 并下载对象。"""
        content, _content_type = self._get_data_client().download_object_by_url(
            file_url
        )
        return BytesIO(content)

    def _get_data_client(self) -> DataClient:
        if self._data is None:
            self._data = get_data_client()
        return self._data


class GatewayMessageBusClient:
    """把网关的逻辑消息操作委托给 backend-data。"""

    def __init__(self, data_client: DataClient | None = None) -> None:
        self._data = data_client
        self.is_available = False
        self.poll_seconds = _read_positive_float(
            "BACKEND_DATA_MESSAGE_POLL_SECONDS",
            DEFAULT_MESSAGE_POLL_SECONDS,
        )
        self.retry_seconds = _read_positive_float(
            "BACKEND_DATA_RETRY_SECONDS",
            DEFAULT_DATA_RETRY_SECONDS,
        )

    async def ensure_ready(self) -> dict[str, Any]:
        status = await self._get_data_client().ensure_message_broker()
        self.is_available = status.get("connected") is True
        return status

    async def publish(
        self,
        *,
        platform: str,
        bot_id: str,
        payload: str,
    ) -> dict[str, Any]:
        result = await self._get_data_client().publish_inbound_message(
            platform=platform,
            bot_id=bot_id,
            payload=payload,
        )
        self.is_available = True
        return result

    async def claim(self) -> dict[str, Any] | None:
        result = await self._get_data_client().claim_outbound_message(
            timeout_seconds=self.poll_seconds,
        )
        self.is_available = True
        return result

    async def acknowledge(self, receipt_id: str) -> None:
        await self._get_data_client().acknowledge_outbound_message(receipt_id)

    async def reject(self, receipt_id: str) -> None:
        await self._get_data_client().reject_outbound_message(receipt_id)

    async def close(self) -> None:
        self.is_available = False
        if self._data is not None:
            await self._data.aclose()

    def _get_data_client(self) -> DataClient:
        if self._data is None:
            self._data = get_data_client()
        return self._data


storage_client = GatewayStorageClient()
message_bus_client = GatewayMessageBusClient()
