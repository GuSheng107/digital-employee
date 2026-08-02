"""仅供 backend-share/data-client 调用的基础设施路由。

注意：本模块原有的 4 个 HTTP 消息代理端点（``/inbound``、
``/outbound/claim``、``/outbound/ack``、``/outbound/nack``）已删除，
因为 backend-gateway 已切换为通过 ``backend-share/rabbitmq-client`` 直连
RabbitMQ 的 AMQP 消费模式，不再走 HTTP 轮询。保留 ``/topology`` 端点，
因为 ``scripts/start-all.py`` 启动验证流程仍通过 HTTP 触发 backend-data
声明单位拓扑（``digital_employee.events`` + DLX/DLQ），且
``app/main.py`` lifespan 中已自动调用 ``ensure_topology()``。
"""

from __future__ import annotations

from api_common import ApiResponse, success_response
from fastapi import APIRouter

from app.services.message_broker_service import get_message_broker_service

router = APIRouter()


@router.post("/message-broker/topology", response_model=ApiResponse)
async def ensure_message_broker_topology() -> dict:
    """由 backend-data 建立并核验 MQ 拓扑（digital_employee.events + DLX/DLQ）。

    保留原因：``scripts/start-all.py`` 启动验证流程通过 HTTP POST 触发
    backend-data 声明统一拓扑（与 gateway 直连 AMQP 的幂等 declare 解耦），
    且 ``app/main.py`` lifespan 中已自动调用 ``ensure_topology()``。
    """
    result = await get_message_broker_service().ensure_topology()
    return success_response(result)
