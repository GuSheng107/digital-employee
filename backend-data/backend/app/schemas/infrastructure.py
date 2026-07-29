"""backend-data 对其他服务公开的基础设施访问契约。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class PublishInboundMessageRequest(BaseModel):
    """发布网关标准化入站消息。"""

    platform: str = Field(..., min_length=1, max_length=64)
    bot_id: str = Field(..., min_length=1, max_length=64)
    payload: str = Field(..., min_length=1)


class MessageReceiptRequest(BaseModel):
    """确认或释放一条已领取消息。"""

    receipt_id: str = Field(..., min_length=1, max_length=64)
