"""仅供 backend-share/data-client 调用的基础设施路由。

注意：本模块原有的 4 个 HTTP 消息代理端点（``/inbound``、
``/outbound/claim``、``/outbound/ack``、``/outbound/nack``）已删除，
因为 backend-gateway 已切换为通过 ``backend-share/rabbitmq-client`` 直连
RabbitMQ 的 AMQP 消费模式，不再走 HTTP 轮询。仅保留 ``/topology`` 端点，
因为 ``scripts/start-all.py`` 启动验证流程仍通过 HTTP 触发 backend-data
自身初始化 MQ 拓扑，且 ``app/main.py`` 的 lifespan shutdown 仍调用
``MessageBrokerService.close()`` 释放连接。
"""

from __future__ import annotations

from api_common import ApiResponse, success_response
from fastapi import APIRouter

from app.services.message_broker_service import get_message_broker_service

router = APIRouter()


@router.post("/message-broker/topology", response_model=ApiResponse)
async def ensure_message_broker_topology() -> dict:
    """由 backend-data 建立并核验 MQ 拓扑。

    保留原因：``scripts/start-all.py`` 启动验证流程通过 HTTP POST 触发
    backend-data 自身初始化 RabbitMQ 拓扑（与 gateway 直连 AMQP 的路径解耦），
    且 ``app/main.py`` lifespan shutdown 时调用 ``close()`` 释放连接。
    """
    result = await get_message_broker_service().ensure_topology()
    return success_response(result)
