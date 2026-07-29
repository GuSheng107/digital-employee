"""非 HTTP 场景的 Span 与载荷采集。"""

from __future__ import annotations

import json
import time
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from observability.context import (
    TraceContext,
    bind_trace_context,
    current_trace_context,
    reset_trace_context,
)
from observability.enums import (
    SpanKind,
    TraceEventType,
    TraceLevel,
    TracePayloadType,
    TraceService,
    TraceStatus,
    TraceTrigger,
)
from observability.middleware import TraceSink
from observability.sanitize import sanitize_value
from observability.schemas import (
    TraceBatch,
    TraceEvent,
    TracePayload,
    TraceRecord,
    TraceSpan,
)


@asynccontextmanager
async def trace_operation(
    *,
    service: TraceService,
    kind: SpanKind,
    operation: str,
    trigger: TraceTrigger,
    event_type: TraceEventType,
    payload_type: TracePayloadType,
    payload: Any,
    sink: TraceSink,
    trace_id: UUID | None = None,
    parent_span_id: UUID | None = None,
    attributes: dict[str, Any] | None = None,
) -> AsyncIterator[TraceContext]:
    """采集 MQ、IM、外部接口或 AI 等非 HTTP 操作。"""
    active = current_trace_context()
    resolved_trace_id = trace_id or (active.trace_id if active else uuid4())
    resolved_parent_span_id = (
        parent_span_id
        if parent_span_id is not None
        else (active.span_id if active else None)
    )
    span_id = uuid4()
    context = TraceContext(trace_id=resolved_trace_id, span_id=span_id)
    token = bind_trace_context(context)
    started_at = datetime.now(UTC)
    started_ns = time.perf_counter_ns()
    status = TraceStatus.SUCCESS
    error_message: str | None = None
    try:
        yield context
    except Exception as exc:
        status = TraceStatus.ERROR
        error_message = f"{type(exc).__name__}: {exc}"
        raise
    finally:
        ended_at = datetime.now(UTC)
        duration_ms = max(0, (time.perf_counter_ns() - started_ns) // 1_000_000)
        sanitized_payload = sanitize_value(payload)
        serialized_payload = json.dumps(
            sanitized_payload,
            ensure_ascii=False,
            default=str,
        ).encode("utf-8")
        batch = TraceBatch(
            trace=TraceRecord(
                trace_id=resolved_trace_id,
                trigger=trigger,
                name=operation,
                status=status,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
                root_service=service,
                error_message=error_message,
            ),
            spans=[
                TraceSpan(
                    span_id=span_id,
                    trace_id=resolved_trace_id,
                    parent_span_id=resolved_parent_span_id,
                    service=service,
                    kind=kind,
                    operation=operation,
                    status=status,
                    started_at=started_at,
                    ended_at=ended_at,
                    duration_ms=duration_ms,
                    attributes=attributes or {},
                    error_message=error_message,
                )
            ],
            events=[
                TraceEvent(
                    trace_id=resolved_trace_id,
                    span_id=span_id,
                    service=service,
                    event_type=event_type,
                    level=(
                        TraceLevel.ERROR
                        if status == TraceStatus.ERROR
                        else TraceLevel.INFO
                    ),
                    name=operation,
                    occurred_at=ended_at,
                    attributes=attributes or {},
                )
            ],
            payloads=[
                TracePayload(
                    trace_id=resolved_trace_id,
                    span_id=span_id,
                    service=service,
                    payload_type=payload_type,
                    content_type="application/json",
                    content=sanitized_payload,
                    size_bytes=len(serialized_payload),
                    created_at=started_at,
                )
            ],
        )
        try:
            await sink(batch)
        except Exception:
            pass
        reset_trace_context(token)
