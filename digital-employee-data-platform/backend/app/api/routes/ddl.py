from fastapi import APIRouter, Request

from app.schemas.common import ApiResponse
from app.schemas.ddl import DdlTableDefinition
from app.services.ddl_service import DdlService
from app.utils.response import success_response


router = APIRouter()


@router.post("/tables/preview", response_model=ApiResponse)
def preview_create_table(payload: DdlTableDefinition) -> dict:
    data = DdlService().preview(payload)
    return success_response(data.model_dump())


@router.post("/tables", response_model=ApiResponse)
def execute_create_table(payload: DdlTableDefinition, request: Request) -> dict:
    data = DdlService().execute(payload, request=request)
    return success_response(data, message="table created")
