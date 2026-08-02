"""backend-data 对其他服务公开的基础设施访问契约。

保留原因：本模块原有的 ``PublishInboundMessageRequest`` 与
``MessageReceiptRequest`` 两个 schema 已随 HTTP 消息代理端点一同删除
（gateway 已切 AMQP 直连）。保留空模块与 pydantic import 以维持
``app.schemas.infrastructure`` 包的可导入性，后续若新增基础设施契约
（如 MQ 拓扑校验、DLQ 查询请求体）可直接在此添加。
"""

from __future__ import annotations

from pydantic import BaseModel, Field  # noqa: F401  保留以备后续新增 schema 复用
