"""backend-data 服务 HTTP 客户端封装。

供其他后端服务调用 backend-data 的基础设施能力（如 Minio 文件上传）。
通过环境变量 BACKEND_DATA_BASE_URL 配置 backend-data 地址，
通过 BACKEND_DATA_API_KEY 配置 API Key。
"""

import os
from typing import Any

import httpx


class DataClient:
    """backend-data HTTP 客户端。

    所有基础设施访问（DB/Redis/Minio）统一通过 backend-data 提供，
    其他服务不直连基础设施。
    """

    def __init__(
        self,
        base_url: str | None = None,
        api_key: str | None = None,
        timeout: float = 30.0,
    ) -> None:
        self._base_url = (base_url or os.environ.get("BACKEND_DATA_BASE_URL", "http://127.0.0.1:8010")).rstrip("/")
        self._api_key = api_key or os.environ.get("BACKEND_DATA_API_KEY", "")
        self._timeout = timeout

    def upload_file(
        self,
        *,
        prefix: str,
        filename: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict[str, Any]:
        """上传文件到 backend-data（最终存储到 Minio）。

        Args:
            prefix: 存储路径前缀，如 "avatars/1"（avatars/{user_id}）
            filename: 原始文件名
            data: 文件二进制内容
            content_type: MIME 类型

        Returns:
            {"object_name": str, "file_url": str}

        Raises:
            RuntimeError: backend-data 返回失败或网络异常
        """
        url = f"{self._base_url}/api/v1/storage/upload"
        headers = {}
        if self._api_key:
            headers["X-API-Key"] = self._api_key

        with httpx.Client(timeout=self._timeout) as client:
            response = client.post(
                url,
                headers=headers,
                files={"file": (filename, data, content_type)},
                data={"prefix": prefix},
            )
            response.raise_for_status()

        body = response.json()
        if not body.get("success"):
            raise RuntimeError(body.get("message", "backend-data upload failed"))

        return body.get("data", {})


_data_client: DataClient | None = None


def get_data_client() -> DataClient:
    """获取全局 DataClient 单例。"""
    global _data_client
    if _data_client is None:
        _data_client = DataClient()
    return _data_client
