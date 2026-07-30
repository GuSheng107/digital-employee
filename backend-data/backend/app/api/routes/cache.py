from api_common import ApiResponse, success_response
from fastapi import APIRouter

from app.services.cache_service import CacheService

router = APIRouter()


@router.post("/test", response_model=ApiResponse)
def write_cache_test() -> dict:
    return success_response(CacheService().write_test_key())


@router.get("/test", response_model=ApiResponse)
def read_cache_test() -> dict:
    return success_response(CacheService().read_test_key())
