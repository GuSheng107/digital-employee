"""仅供 backend-share/data-client 调用的基础设施路由。"""

from __future__ import annotations

from fastapi import APIRouter, Query

from app.core.config import settings
from api_common import ApiResponse, success_response
from app.schemas.infrastructure import (
    MessageReceiptRequest,
    PublishInboundMessageRequest,
)
from app.services.message_broker_service import get_message_broker_service


router = APIRouter()


@router.post("/message-broker/topology", response_model=ApiResponse)
async def ensure_message_broker_topology() -> dict:
    """由 backend-data 建立并核验 MQ 拓扑。"""
    result = await get_message_broker_service().ensure_topology()
    return success_response(result)


@router.post("/message-broker/inbound", response_model=ApiResponse)
async def publish_inbound_message(
    payload: PublishInboundMessageRequest,
) -> dict:
    """发布网关入站消息，调用方无需知道交换机或路由前缀。"""
    result = await get_message_broker_service().publish_inbound(**payload.model_dump())
    return success_response(result)


@router.get("/message-broker/outbound/claim", response_model=ApiResponse)
async def claim_outbound_message(
    timeout_seconds: float = Query(
        default=settings.message_poll_timeout_seconds,
        ge=0.1,
        le=30.0,
    ),
) -> dict:
    """长轮询领取一条带 Redis 租约的出站消息。"""
    result = await get_message_broker_service().claim_outbound(
        timeout_seconds=timeout_seconds,
    )
    return success_response(result)


@router.post("/message-broker/outbound/ack", response_model=ApiResponse)
def acknowledge_outbound_message(payload: MessageReceiptRequest) -> dict:
    """确认网关已成功处理消息。"""
    result = get_message_broker_service().ack_outbound(payload.receipt_id)
    return success_response(result)


@router.post("/message-broker/outbound/nack", response_model=ApiResponse)
def reject_outbound_message(payload: MessageReceiptRequest) -> dict:
    """处理失败时释放消息租约以便重试。"""
    result = get_message_broker_service().nack_outbound(payload.receipt_id)
    return success_response(result)
