"""头像存储公开地址与读取路径测试。"""

from __future__ import annotations

from typing import Any

import pytest

from app.services import storage_service
from app.services.storage_service import StorageService


class _FakeMinio:
    """StorageService 使用的最小 MinIO 测试替身。"""

    def upload_file(self, **_kwargs: Any) -> str:
        """返回模拟私有直链。"""
        return "http://minio.invalid/private/object"

    def download_file_with_content_type(
        self,
        *,
        object_name: str,
    ) -> tuple[bytes, str]:
        """返回对象名，便于断言 avatars 前缀。"""
        return object_name.encode(), "image/png"


def test_avatar_upload_returns_backend_data_public_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """头像上传不能再把私有 MinIO 直链返回给浏览器。"""
    monkeypatch.setattr(storage_service, "get_minio_client", _FakeMinio)
    monkeypatch.setattr(storage_service.time, "time", lambda: 1.234)

    result = StorageService().upload_file(
        prefix="avatars/9",
        filename="photo.png",
        data=b"image",
        content_type="image/png",
    )

    assert result["object_name"] == "avatars/9/1234_photo.png"
    assert result["file_url"] == "/api/v1/storage/avatars/9/1234_photo.png"


def test_avatar_download_is_restricted_to_avatar_prefix(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """公开读取路由只能映射到 avatars/ 对象前缀。"""
    monkeypatch.setattr(storage_service, "get_minio_client", _FakeMinio)

    content, content_type = StorageService().download_avatar("9/photo.png")

    assert content == b"avatars/9/photo.png"
    assert content_type == "image/png"


@pytest.mark.parametrize("avatar_path", ["", "../secret", "9/../secret"])
def test_avatar_download_rejects_invalid_paths(avatar_path: str) -> None:
    """空路径和目录穿越片段必须被拒绝。"""
    with pytest.raises(ValueError, match="invalid avatar path"):
        StorageService().download_avatar(avatar_path)


def test_internal_object_name_rejects_path_traversal() -> None:
    """内部对象上传和下载同样不能接受目录穿越片段。"""
    with pytest.raises(ValueError, match="invalid object name"):
        StorageService().download_object("wechat/../secret")
