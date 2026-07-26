from io import BytesIO

from app.core.config import settings
from app.core.minio_client import get_minio_client


class StorageService:
    test_object_name = "health-check/test-object.txt"
    test_object_content = b"minio-ok"

    def ensure_default_bucket(self) -> dict:
        return get_minio_client().ensure_bucket(settings.minio_default_bucket)

    def list_buckets(self) -> list[dict]:
        return get_minio_client().list_buckets()

    def write_test_object(self) -> dict:
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
        content = get_minio_client().download_file(
            object_name=self.test_object_name,
        ).read().decode("utf-8")
        return {
            "bucket": settings.minio_default_bucket,
            "object_name": self.test_object_name,
            "content": content,
        }
