import time
from io import BytesIO
from urllib.parse import quote, unquote, urlparse
from uuid import uuid4

from app.core.config import settings
from app.core.minio_client import get_minio_client
from app.core.storage_constants import (
    AVATAR_OBJECT_PREFIX,
    AVATAR_ROUTE_PREFIX,
    MAX_OBJECT_NAME_LENGTH,
    STORAGE_ROUTE_PREFIX,
)


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
        content = (
            get_minio_client()
            .download_file(
                object_name=self.test_object_name,
            )
            .read()
            .decode("utf-8")
        )
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
            prefix: 普通业务对象前缀，如 "attachments/agent-1"。
            filename: 原始文件名。
            data: 文件二进制内容。
            content_type: MIME 类型。

        Returns:
            {"object_name": str, "file_url": str}
        """
        normalized_prefix = prefix.strip("/")
        if normalized_prefix and any(
            segment in {"", ".", ".."} for segment in normalized_prefix.split("/")
        ):
            raise ValueError("invalid object prefix")
        if (
            normalized_prefix == AVATAR_OBJECT_PREFIX
            or normalized_prefix.startswith(f"{AVATAR_OBJECT_PREFIX}/")
        ):
            raise ValueError("reserved object prefix")
        safe_filename = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] or "file"
        unique_name = f"{int(time.time() * 1000)}_{uuid4().hex}_{safe_filename}"
        object_name = (
            f"{normalized_prefix}/{unique_name}"
            if normalized_prefix
            else unique_name
        )
        storage_url = get_minio_client().upload_file(
            object_name=object_name,
            data=BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return {
            "object_name": object_name,
            "file_url": storage_url,
        }

    def upload_avatar(
        self,
        *,
        user_id: int,
        filename: str,
        data: bytes,
        content_type: str,
    ) -> dict:
        """上传经过身份服务校验的头像对象。"""
        safe_filename = filename.rsplit("/", 1)[-1].rsplit("\\", 1)[-1] or "avatar"
        object_name = (
            f"{AVATAR_OBJECT_PREFIX}/{user_id}/"
            f"{int(time.time() * 1000)}_{uuid4().hex}_{safe_filename}"
        )
        get_minio_client().upload_file(
            object_name=object_name,
            data=BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        avatar_path = quote(object_name.removeprefix(f"{AVATAR_OBJECT_PREFIX}/"), safe="/")
        return {
            "object_name": object_name,
            "file_url": (
                f"{settings.api_prefix}{STORAGE_ROUTE_PREFIX}"
                f"{AVATAR_ROUTE_PREFIX}/{avatar_path}"
            ),
        }

    def upload_object(
        self,
        *,
        object_name: str,
        data: bytes,
        content_type: str = "application/octet-stream",
    ) -> dict:
        """按调用方给出的业务对象名上传文件。

        该接口供网关等内部服务通过 data-client 使用。对象名由
        backend-data 统一校验，其他服务不接触 MinIO 客户端或桶配置。
        """
        normalized_name = self._normalize_object_name(object_name)
        file_url = get_minio_client().upload_file(
            object_name=normalized_name,
            data=BytesIO(data),
            length=len(data),
            content_type=content_type,
        )
        return {
            "object_name": normalized_name,
            "file_url": file_url,
        }

    def download_object(self, object_name: str) -> tuple[bytes, str]:
        """读取默认业务桶中的内部对象。"""
        normalized_name = self._normalize_object_name(object_name)
        return get_minio_client().download_file_with_content_type(
            object_name=normalized_name,
        )

    def download_object_by_url(self, file_url: str) -> tuple[bytes, str]:
        """解析 backend-data 生成的存储 URL 并读取对象。

        URL 的协议、端点和桶必须与当前配置一致，避免调用方借该接口
        把任意外部 URL 或其他桶路径转换为内部读取请求。
        """
        parsed = urlparse(file_url)
        expected_scheme = "https" if settings.minio_secure else "http"
        bucket_prefix = f"/{settings.minio_default_bucket}/"
        if (
            parsed.scheme != expected_scheme
            or parsed.netloc != settings.minio_endpoint
            or not parsed.path.startswith(bucket_prefix)
            or parsed.query
            or parsed.fragment
        ):
            raise ValueError("invalid storage url")
        object_name = unquote(parsed.path.removeprefix(bucket_prefix))
        return self.download_object(object_name)

    def download_avatar(self, avatar_path: str) -> tuple[bytes, str]:
        """读取公开头像对象。

        公开路由只能访问 ``avatars/`` 前缀，不能借此读取业务桶中的其他对象。

        Args:
            avatar_path: 去掉 ``avatars/`` 前缀后的对象路径。

        Returns:
            ``(文件字节, MIME 类型)``。

        Raises:
            ValueError: 路径为空或包含 ``.`` / ``..`` 非法片段。
        """
        normalized_path = avatar_path.strip("/")
        path_segments = normalized_path.split("/")
        if not normalized_path or any(
            segment in {"", ".", ".."} for segment in path_segments
        ):
            raise ValueError("invalid avatar path")
        object_name = f"{AVATAR_OBJECT_PREFIX}/{normalized_path}"
        content, content_type = self.download_object(object_name)
        if not content_type.startswith("image/"):
            raise ValueError("invalid avatar content type")
        return content, content_type

    @staticmethod
    def _normalize_object_name(object_name: str) -> str:
        normalized_name = object_name.strip("/")
        segments = normalized_name.split("/")
        if (
            not normalized_name
            or len(normalized_name) > MAX_OBJECT_NAME_LENGTH
            or any(segment in {"", ".", ".."} for segment in segments)
        ):
            raise ValueError("invalid object name")
        return normalized_name
