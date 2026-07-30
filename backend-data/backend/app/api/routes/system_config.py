from api_common import ApiResponse, success_response
from fastapi import APIRouter

from app.core.config import settings
from app.schemas.system_config import TestConnectionsRequest
from app.services.health_service import HealthService

router = APIRouter()


@router.get("/config", response_model=ApiResponse)
def get_system_config() -> dict:
    return success_response(settings.public_config())


@router.post("/test-connections", response_model=ApiResponse)
def test_connections(payload: TestConnectionsRequest | None = None) -> dict:
    target = payload.target if payload else "all"
    statuses = HealthService().test_dependencies(target=target)
    return success_response(statuses.model_dump())
