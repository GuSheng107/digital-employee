from io import BytesIO
from urllib.parse import urlparse

from minio import Minio
from urllib3 import PoolManager, Timeout

from app.core.config import settings


class MinioClientWrapper:
    """Centralized MinIO wrapper for bucket, upload, download, and URL parsing."""

    def __init__(self) -> None:
        self.endpoint = settings.minio_endpoint
        self.secure = settings.minio_secure
        self.access_key = settings.minio_access_key
        self.secret_key = settings.minio_secret_key
        self.bucket_name = settings.minio_default_bucket
        self.client: Minio | None = None
        self._initialized = False

    def init_client(self) -> None:
        if self._initialized:
            return

        self.client = Minio(
            endpoint=self.endpoint,
            access_key=self.access_key,
            secret_key=self.secret_key,
            secure=self.secure,
            http_client=PoolManager(
                timeout=Timeout(
                    connect=settings.dependency_timeout_seconds,
                    read=settings.dependency_timeout_seconds,
                ),
                retries=False,
            ),
        )
        if not self.client.bucket_exists(self.bucket_name):
            self.client.make_bucket(self.bucket_name)
        self._initialized = True

    def ensure_bucket(self, bucket_name: str | None = None) -> dict:
        self.init_client()
        if self.client is None:
            raise RuntimeError("MinIO client is not initialized.")
        client = self.client
        bucket = bucket_name or self.bucket_name
        if not client.bucket_exists(bucket):
            client.make_bucket(bucket)
        return {"bucket": bucket, "exists": True}

    def list_buckets(self) -> list[dict]:
        client = self._require_client()
        return [
            {
                "name": bucket.name,
                "creation_date": (
                    bucket.creation_date.isoformat() if bucket.creation_date else None
                ),
            }
            for bucket in client.list_buckets()
        ]

    def upload_file(
        self,
        *,
        object_name: str,
        data: BytesIO,
        length: int,
        content_type: str = "application/octet-stream",
        bucket_name: str | None = None,
    ) -> str:
        client = self._require_client()
        bucket = bucket_name or self.bucket_name
        self.ensure_bucket(bucket)
        data.seek(0)
        client.put_object(
            bucket_name=bucket,
            object_name=object_name,
            data=data,
            length=length,
            content_type=content_type,
        )
        return self.build_file_url(object_name=object_name, bucket_name=bucket)

    def download_file(
        self,
        *,
        object_name: str,
        bucket_name: str | None = None,
    ) -> BytesIO:
        client = self._require_client()
        response = client.get_object(
            bucket_name=bucket_name or self.bucket_name,
            object_name=object_name,
        )
        try:
            return BytesIO(response.read())
        finally:
            response.close()
            response.release_conn()

    def download_file_with_content_type(
        self,
        *,
        object_name: str,
        bucket_name: str | None = None,
    ) -> tuple[bytes, str]:
        """下载对象内容及其存储时记录的 MIME 类型。

        Args:
            object_name: MinIO 对象名。
            bucket_name: 可选桶名，默认使用业务桶。

        Returns:
            ``(文件字节, MIME 类型)``。
        """
        client = self._require_client()
        bucket = bucket_name or self.bucket_name
        stat = client.stat_object(bucket_name=bucket, object_name=object_name)
        response = client.get_object(bucket_name=bucket, object_name=object_name)
        try:
            content = response.read()
        finally:
            response.close()
            response.release_conn()
        return content, stat.content_type or "application/octet-stream"

    def build_file_url(self, *, object_name: str, bucket_name: str | None = None) -> str:
        scheme = "https" if self.secure else "http"
        return f"{scheme}://{self.endpoint}/{bucket_name or self.bucket_name}/{object_name}"

    def get_object_name_from_url(self, file_url: str) -> str:
        parsed = urlparse(file_url)
        path = parsed.path.lstrip("/")
        bucket_prefix = self.bucket_name + "/"
        if path.startswith(bucket_prefix):
            return path[len(bucket_prefix) :]

        parts = path.split("/", 1)
        if len(parts) > 1:
            return parts[1]
        return path

    def _require_client(self) -> Minio:
        self.init_client()
        if self.client is None:
            raise RuntimeError("MinIO client is not initialized.")
        return self.client


_minio_client_wrapper: MinioClientWrapper | None = None


def get_minio_client() -> MinioClientWrapper:
    global _minio_client_wrapper
    if _minio_client_wrapper is None:
        _minio_client_wrapper = MinioClientWrapper()
    return _minio_client_wrapper
