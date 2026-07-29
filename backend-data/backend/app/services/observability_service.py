"""统一链路日志业务服务。"""

from __future__ import annotations

from datetime import datetime
from uuid import UUID

from api_common import ValidationError
from observability import (
    SpanKind,
    TraceBatch,
    TraceCallStatus,
    TraceEventType,
    TraceLevel,
    TracePayloadType,
    TraceService,
    TraceStatus,
    TraceTrigger,
)
from sqlalchemy.orm import Session

from app.repositories.observability_repo import ObservabilityRepository


class ObservabilityService:
    """链路日志写入、查询和元数据服务。"""

    def __init__(self, session: Session) -> None:
        self.repository = ObservabilityRepository(session)

    def ingest(self, batch: TraceBatch) -> None:
        """持久化上报批次。"""
        self.repository.ingest(batch)

    def list_traces(
        self,
        *,
        trace_id: UUID | None,
        started_from: datetime | None,
        started_to: datetime | None,
        trigger: TraceTrigger | None,
        service: TraceService | None,
        call_status: TraceCallStatus | None,
        keyword: str | None,
        page: int,
        page_size: int,
    ) -> dict:
        """分页查询链路摘要。"""
        if (
            started_from is not None
            and started_to is not None
            and started_from > started_to
        ):
            raise ValidationError(message="开始时间不能晚于结束时间")
        page_slice = self.repository.list_traces(
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
        call_statuses = self.repository.get_trace_call_statuses(
            [item.trace_id for item in page_slice.items]
        )
        serialized_items = []
        for item in page_slice.items:
            serialized = self.repository.model_dict(item)
            serialized["call_status"] = call_statuses.get(
                item.trace_id,
                TraceCallStatus.SUCCESS.value,
            )
            serialized_items.append(serialized)
        return page_slice.response(serialized_items)

    def get_trace_detail(self, trace_id: UUID) -> dict | None:
        """读取链路摘要、Span 树原始节点与事件。"""
        trace = self.repository.get_trace(trace_id)
        if trace is None:
            return None
        serialized_trace = self.repository.model_dict(trace)
        serialized_trace["call_status"] = (
            self.repository.get_trace_call_statuses([trace_id]).get(
                trace_id,
                TraceCallStatus.SUCCESS.value,
            )
        )
        return {
            "trace": serialized_trace,
            "spans": [
                self.repository.model_dict(item)
                for item in self.repository.list_spans(trace_id)
            ],
            "events": [
                self.repository.model_dict(item)
                for item in self.repository.list_events(trace_id)
            ],
        }

    def list_payloads(self, span_id: UUID) -> list[dict]:
        """读取 Span 载荷元数据，正文由分块接口按需读取。"""
        return [
            self.repository.model_dict(item)
            for item in self.repository.list_payloads(span_id)
        ]

    def list_payload_chunks(
        self,
        payload_id: UUID,
        *,
        chunk_from: int,
        chunk_limit: int,
    ) -> dict:
        """分页读取长载荷正文。"""
        items, total = self.repository.list_payload_chunks(
            payload_id,
            chunk_from=chunk_from,
            chunk_limit=chunk_limit,
        )
        return {
            "items": [self.repository.model_dict(item) for item in items],
            "total": total,
            "chunk_from": chunk_from,
            "chunk_limit": chunk_limit,
        }

    @staticmethod
    def metadata() -> dict[str, list[str]]:
        """向前端提供唯一可信的静态枚举值。"""
        return {
            "triggers": [item.value for item in TraceTrigger],
            "services": [item.value for item in TraceService],
            "span_kinds": [item.value for item in SpanKind],
            "statuses": [item.value for item in TraceStatus],
            "levels": [item.value for item in TraceLevel],
            "event_types": [item.value for item in TraceEventType],
            "payload_types": [item.value for item in TracePayloadType],
            "call_statuses": [item.value for item in TraceCallStatus],
        }
