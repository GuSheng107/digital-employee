from fastapi import APIRouter

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
