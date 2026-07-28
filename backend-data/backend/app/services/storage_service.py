import time
from io import BytesIO

from app.core.config import settings
from app.core.minio_client import get_minio_client


class StorageService:
    """MinIO 对象存储业务编排层。

    封装默认桶管理及健康检查对象的读写测试逻辑。
    """

    test_object_name = "health-check/test-object.txt"
    test_object_content = b"minio-ok"

    def ensure_default_bucket(self) -> dict:
        """确保默认存储桶存在，不存在则创建。

        Returns:
            桶名及存在性信息。
        """
        return get_minio_client().ensure_bucket(settings.minio_default_bucket)

    def list_buckets(self) -> list[dict]:
        """列出当前 MinIO 实例下的全部存储桶。

        Returns:
            桶名与创建时间组成的字典列表。
        """
        return get_minio_client().list_buckets()

    def write_test_object(self) -> dict:
        """写入用于健康检查的测试对象。

        Returns:
            桶名、对象名、可访问 URL 及写入内容。
        """
        file_url = get_minio_client().upload_file(
            object_name=self.test_object_name,
            data=BytesIO(self.test_object_content),
            length=len(self.test_object_content),
            content_type="text/plain",
        )
        return {
            "bucket": settings.minio_default_bucket,
            "object_name": self.test_object_name,
            "file_url": file_url,
            "content": self.test_object_content.decode("utf-8"),
        }

    def read_test_object(self) -> dict:
        """读取已写入的健康检查测试对象内容。

        Returns:
            桶名、对象名及读取到的文本内容。
        """
        content = get_minio_client().download_file(
            object_name=self.test_object_name,
        ).read().decode("utf-8")
        return {
            "bucket": settings.minio_default_bucket,
            "object_name": self.test_object_name,
            "content": content,
        }

    def upload_file(
        self,
        *,
        prefix: str,
        filename: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict:
        """通用文件上传，按 {prefix}/{timestamp}_{filename} 存储到 Minio 默认 bucket。

        Args:
            prefix: 对象名前缀，如 "avatars/1"（avatars/{user_id}）。
            filename: 原始文件名。
            data: 文件二进制内容。
            content_type: MIME 类型。

        Returns:
            {"object_name": str, "file_url": str}
        """
        object_name = f"{prefix}/{int(time.time() * 1000)}_{filename}"
        file_url = get_minio_client().upload_file(
            object_name=object_name,
            data=BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return {
            "object_name": object_name,
            "file_url": file_url,
        }
