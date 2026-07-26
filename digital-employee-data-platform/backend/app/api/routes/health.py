from fastapi import APIRouter

from app.schemas.common import ApiResponse
from app.services.health_service import HealthService
from app.utils.response import success_response


router = APIRouter()


@router.get("", response_model=ApiResponse)
def api_health() -> dict:
    return success_response({"status": "healthy"})


@router.get("/dependencies", response_model=ApiResponse)
def dependencies() -> dict:
    statuses = HealthService().test_dependencies()
    return success_response(statuses.model_dump())
