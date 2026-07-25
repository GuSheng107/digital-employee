from uuid import UUID

from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.core.database import get_core_db_session
from app.repositories.data_item_repo import DataItemRepository
from app.schemas.common import ApiResponse
from app.schemas.data_item import DataItemCreate, DataItemRead, DataItemUpdate
from app.services.data_item_service import DataItemService
from app.utils.response import success_response


router = APIRouter()


def get_service(session: Session = Depends(get_core_db_session)) -> DataItemService:
    return DataItemService(DataItemRepository(session))


@router.post("", response_model=ApiResponse)
def create_data_item(
    payload: DataItemCreate,
    service: DataItemService = Depends(get_service),
) -> dict:
    item = service.create(payload)
    return success_response(DataItemRead.model_validate(item).model_dump(mode="json"))


@router.get("", response_model=ApiResponse)
def list_data_items(
    namespace: str | None = Query(default=None),
    service: DataItemService = Depends(get_service),
) -> dict:
    items = service.list(namespace=namespace)
    data = [DataItemRead.model_validate(item).model_dump(mode="json") for item in items]
    return success_response(data)


@router.get("/{item_id}", response_model=ApiResponse)
def get_data_item(
    item_id: UUID,
    service: DataItemService = Depends(get_service),
) -> dict:
    item = service.get(item_id)
    return success_response(DataItemRead.model_validate(item).model_dump(mode="json"))


@router.put("/{item_id}", response_model=ApiResponse)
def update_data_item(
    item_id: UUID,
    payload: DataItemUpdate,
    service: DataItemService = Depends(get_service),
) -> dict:
    item = service.update(item_id, payload)
    return success_response(DataItemRead.model_validate(item).model_dump(mode="json"))


@router.delete("/{item_id}", response_model=ApiResponse)
def delete_data_item(
    item_id: UUID,
    service: DataItemService = Depends(get_service),
) -> dict:
    service.delete(item_id)
    return success_response({"id": str(item_id)}, message="deleted")
