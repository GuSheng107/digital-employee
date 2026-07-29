"""跨服务传输的链路日志契约。"""

from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from pydantic import BaseModel, Field

from observability.enums import (
    SpanKind,
    TraceEventType,
    TraceLevel,
    TracePayloadType,
    TraceService,
    TraceStatus,
    TraceTrigger,
)


def utc_now() -> datetime:
    """返回带时区的 UTC 时间。"""
    return datetime.now(UTC)


class TraceRecord(BaseModel):
    """一次完整调用链的摘要。"""

    trace_id: UUID
    trigger: TraceTrigger
    name: str
    status: TraceStatus
    started_at: datetime
    ended_at: datetime
    duration_ms: int = Field(ge=0)
    root_service: TraceService
    http_method: str | None = None
    http_path: str | None = None
    http_status: int | None = None
    error_message: str | None = None


class TraceSpan(BaseModel):
    """调用链树节点。"""

    span_id: UUID = Field(default_factory=uuid4)
    trace_id: UUID
    parent_span_id: UUID | None = None
    service: TraceService
    kind: SpanKind
    operation: str
    status: TraceStatus
    started_at: datetime
    ended_at: datetime
    duration_ms: int = Field(ge=0)
    attributes: dict[str, Any] = Field(default_factory=dict)
    error_message: str | None = None


class TraceEvent(BaseModel):
    """Span 内的重要事件。"""

    event_id: UUID = Field(default_factory=uuid4)
    trace_id: UUID
    span_id: UUID
    service: TraceService
    event_type: TraceEventType
    level: TraceLevel
    name: str
    occurred_at: datetime = Field(default_factory=utc_now)
    attributes: dict[str, Any] = Field(default_factory=dict)


class TracePayload(BaseModel):
    """用于排障的完整业务载荷。"""

    payload_id: UUID = Field(default_factory=uuid4)
    trace_id: UUID
    span_id: UUID
    service: TraceService
    payload_type: TracePayloadType
    content_type: str
    content: Any
    size_bytes: int = Field(ge=0)
    created_at: datetime = Field(default_factory=utc_now)


class TraceBatch(BaseModel):
    """一次上报批次。"""

    trace: TraceRecord
    spans: list[TraceSpan] = Field(default_factory=list)
    events: list[TraceEvent] = Field(default_factory=list)
    payloads: list[TracePayload] = Field(default_factory=list)
