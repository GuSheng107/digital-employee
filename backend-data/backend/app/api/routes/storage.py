from fastapi import APIRouter, File, Form, UploadFile

from app.schemas.common import ApiResponse
from app.services.storage_service import StorageService
from app.utils.response import success_response


router = APIRouter()


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
