from api_common import ResourceNotFoundError, ValidationError
from fastapi import APIRouter, File, Form, Query, Response, UploadFile
from minio.error import S3Error

from app.core.storage_constants import (
    AVATAR_ROUTE_PREFIX,
    IMMUTABLE_ASSET_CACHE_CONTROL,
)
from app.schemas.common import ApiResponse
from app.services.storage_service import StorageService
from app.utils.response import success_response


router = APIRouter()
public_router = APIRouter()


@public_router.get(f"{AVATAR_ROUTE_PREFIX}/{{avatar_path:path}}")
def read_avatar(avatar_path: str) -> Response:
    """公开读取头像。

    浏览器的 ``img`` 请求无法携带业务 API Key，因此头像使用独立只读路由。
    路由被严格限制在 MinIO ``avatars/`` 前缀，不暴露桶中其他业务对象。
    """
    try:
        content, content_type = StorageService().download_avatar(avatar_path)
    except ValueError as exc:
        raise ValidationError(message="头像路径无效") from exc
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchObject"}:
            raise ResourceNotFoundError(message="头像不存在") from exc
        raise
    return Response(
        content=content,
        media_type=content_type,
        headers={
            "Cache-Control": IMMUTABLE_ASSET_CACHE_CONTROL,
            "X-Content-Type-Options": "nosniff",
        },
    )


@router.post("/buckets/ensure", response_model=ApiResponse)
def ensure_default_bucket() -> dict:
    return success_response(StorageService().ensure_default_bucket())


@router.get("/buckets", response_model=ApiResponse)
def list_buckets() -> dict:
    return success_response(StorageService().list_buckets())


@router.post("/test-object", response_model=ApiResponse)
def write_test_object() -> dict:
    return success_response(StorageService().write_test_object())


@router.get("/test-object", response_model=ApiResponse)
def read_test_object() -> dict:
    return success_response(StorageService().read_test_object())


@router.post("/upload", response_model=ApiResponse)
def upload_file(
    file: UploadFile = File(...),
    prefix: str = Form(default=""),
) -> dict:
    """通用文件上传接口。

    接收 multipart 文件，存储到 Minio，返回可访问 URL。
    prefix 用于指定存储路径前缀，如 "avatars/1"。
    """
    content = file.file.read()
    result = StorageService().upload_file(
        prefix=prefix,
        filename=file.filename or "",
        data=content,
        content_type=file.content_type or "application/octet-stream",
    )
    return success_response(result)


@router.post("/objects", response_model=ApiResponse)
def upload_object(
    file: UploadFile = File(...),
    object_name: str = Form(...),
) -> dict:
    """按业务对象名上传内部文件；仅供 data-client 服务调用。"""
    content = file.file.read()
    try:
        result = StorageService().upload_object(
            object_name=object_name,
            data=content,
            content_type=file.content_type or "application/octet-stream",
        )
    except ValueError as exc:
        raise ValidationError(message="对象名称无效") from exc
    return success_response(result)


@router.get("/objects/content")
def download_object(
    object_name: str = Query(..., min_length=1),
) -> Response:
    """下载内部对象，二进制内容不套 JSON 响应信封。"""
    try:
        content, content_type = StorageService().download_object(object_name)
    except ValueError as exc:
        raise ValidationError(message="对象名称无效") from exc
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchObject"}:
            raise ResourceNotFoundError(message="文件不存在") from exc
        raise
    return Response(
        content=content,
        media_type=content_type,
        headers={"X-Content-Type-Options": "nosniff"},
    )


@router.get("/objects/by-url")
def download_object_by_url(
    file_url: str = Query(..., min_length=1),
) -> Response:
    """按 backend-data 生成的存储 URL 下载内部对象。"""
    try:
        content, content_type = StorageService().download_object_by_url(file_url)
    except ValueError as exc:
        raise ValidationError(message="文件地址无效") from exc
    except S3Error as exc:
        if exc.code in {"NoSuchKey", "NoSuchObject"}:
            raise ResourceNotFoundError(message="文件不存在") from exc
        raise
    return Response(
        content=content,
        media_type=content_type,
        headers={"X-Content-Type-Options": "nosniff"},
    )
