"""统一链路日志上报与查询 API。"""

import gzip
from datetime import datetime
from uuid import UUID

from api_common import ResourceNotFoundError, ValidationError, success_response
from auth_utils import PermissionCode
from fastapi import APIRouter, Depends, Query, Request
from observability import (
    TraceBatch,
    TraceCallStatus,
    TraceService,
    TraceTrigger,
)
from pydantic import ValidationError as PydanticValidationError
from sqlalchemy.orm import Session

from app.api.deps import require_service_or_permission, verify_api_key
from app.core.database import get_core_db_session
from app.services.observability_service import ObservabilityService

router = APIRouter()


@router.post("/events/batch", dependencies=[Depends(verify_api_key)])
async def ingest_trace_batch(
    request: Request,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """接收普通 JSON 或 gzip 压缩的长载荷日志批次。"""
    raw_body = await request.body()
    if request.headers.get("content-encoding", "").lower() == "gzip":
        try:
            raw_body = gzip.decompress(raw_body)
        except OSError as exc:
            raise ValidationError(message="日志上报 gzip 正文无效") from exc
    try:
        payload = TraceBatch.model_validate_json(raw_body)
    except PydanticValidationError as exc:
        raise ValidationError(message="日志上报正文不符合契约") from exc
    ObservabilityService(session).ingest(payload)
    return success_response(None, message="链路日志已接收")


@router.get(
    "/traces",
    dependencies=[
        Depends(
            require_service_or_permission(PermissionCode.OBSERVABILITY_LOG_VIEW)
        )
    ],
)
def list_traces(
    trace_id: UUID | None = None,
    started_from: datetime | None = None,
    started_to: datetime | None = None,
    trigger: TraceTrigger | None = None,
    service: TraceService | None = None,
    call_status: TraceCallStatus | None = None,
    keyword: str | None = Query(default=None, max_length=500),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=20, ge=1, le=100),
    session: Session = Depends(get_core_db_session),
) -> dict:
    """按 traceId、时间、来源、服务、调用状态和内容查询。"""
    data = ObservabilityService(session).list_traces(
        trace_id=trace_id,
        started_from=started_from,
        started_to=started_to,
        trigger=trigger,
        service=service,
        call_status=call_status,
        keyword=keyword,
        page=page,
        page_size=page_size,
    )
    return success_response(data)


@router.get(
    "/traces/{trace_id}",
    dependencies=[
        Depends(
            require_service_or_permission(PermissionCode.OBSERVABILITY_LOG_VIEW)
        )
    ],
)
def get_trace_detail(
    trace_id: UUID,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """读取完整链路结构，载荷按 Span 单独懒加载。"""
    data = ObservabilityService(session).get_trace_detail(trace_id)
    if data is None:
        raise ResourceNotFoundError(message="链路日志不存在")
    return success_response(data)


@router.get(
    "/spans/{span_id}/payloads",
    dependencies=[
        Depends(
            require_service_or_permission(PermissionCode.OBSERVABILITY_LOG_VIEW)
        )
    ],
)
def list_span_payloads(
    span_id: UUID,
    session: Session = Depends(get_core_db_session),
) -> dict:
    """读取指定 Span 的完整业务载荷。"""
    return success_response(ObservabilityService(session).list_payloads(span_id))


@router.get(
    "/payloads/{payload_id}/chunks",
    dependencies=[
        Depends(
            require_service_or_permission(PermissionCode.OBSERVABILITY_LOG_VIEW)
        )
    ],
)
def list_payload_chunks(
    payload_id: UUID,
    chunk_from: int = Query(default=0, ge=0),
    chunk_limit: int = Query(default=4, ge=1, le=100),
    session: Session = Depends(get_core_db_session),
) -> dict:
    """按需读取长载荷正文分块。"""
    return success_response(
        ObservabilityService(session).list_payload_chunks(
            payload_id,
            chunk_from=chunk_from,
            chunk_limit=chunk_limit,
        )
    )


@router.get(
    "/metadata",
    dependencies=[
        Depends(
            require_service_or_permission(PermissionCode.OBSERVABILITY_LOG_VIEW)
        )
    ],
)
def get_observability_metadata() -> dict:
    """返回链路日志筛选枚举。"""
    return success_response(ObservabilityService.metadata())
