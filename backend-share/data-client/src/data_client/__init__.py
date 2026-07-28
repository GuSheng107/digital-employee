"""backend-data 服务的 HTTP 客户端封装。

供其他后端服务（如 backend-auth）调用 backend-data 的基础设施能力
（如 Minio 文件上传），统一走 HTTP API，不直连基础设施。

典型用法：
    from data_client import DataClient, get_data_client

    client = get_data_client()
    result = client.upload_file(
        prefix="avatars/1",
        filename="logo.png",
        data=file_bytes,
        content_type="image/png",
    )
    # result = {"object_name": "...", "file_url": "..."}
"""

from data_client.client import DataClient, get_data_client

__all__ = ["DataClient", "get_data_client"]
