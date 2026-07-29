"""FastAPI/Starlette 全链路日志中间件。"""

from __future__ import annotations

import time
import json
from collections.abc import Awaitable, Callable, Iterable
from datetime import UTC, datetime
from typing import Any
from uuid import UUID, uuid4

from starlette.types import ASGIApp, Message, Receive, Scope, Send

from observability.context import (
    PARENT_SPAN_ID_HEADER,
    TRACE_SUPPRESS_HEADER,
    TRACE_ID_HEADER,
    TRACEPARENT_HEADER,
    TraceContext,
    bind_trace_context,
    bind_trace_suppressed,
    parse_traceparent,
    parse_uuid,
    reset_trace_context,
    reset_trace_suppressed,
)
from observability.capture import (
    bind_trace_capture,
    captured_events,
    reset_trace_capture,
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
from observability.sanitize import decode_body, sanitize_headers
from observability.schemas import (
    TraceBatch,
    TraceEvent,
    TracePayload,
    TraceRecord,
    TraceSpan,
)

TraceSink = Callable[[TraceBatch], Awaitable[None]]

DEFAULT_EXCLUDED_PATH_PREFIXES = (
    "/docs",
    "/redoc",
    "/openapi.json",
    "/api/v1/health",
    "/health",
    "/assets",
)
MQ_OUTBOUND_CLAIM_PATH = "/api/v1/infrastructure/message-broker/outbound/claim"


class TraceMiddleware:
    """采集 HTTP 请求、响应与跨服务父子关系的 ASGI 中间件。"""

    def __init__(
        self,
        app: ASGIApp,
        *,
        service: TraceService,
        sink: TraceSink,
        excluded_path_prefixes: Iterable[str] = DEFAULT_EXCLUDED_PATH_PREFIXES,
        ingest_path_prefix: str = "/api/v1/observability",
    ) -> None:
        self.app = app
        self.service = service
        self.sink = sink
        self.excluded_path_prefixes = tuple(excluded_path_prefixes)
        self.ingest_path_prefix = ingest_path_prefix

    async def __call__(self, scope: Scope, receive: Receive, send: Send) -> None:
        if scope["type"] != "http":
            await self.app(scope, receive, send)
            return
        headers = self._headers(scope)
        if (
            self._is_excluded(str(scope.get("path", "")))
            or headers.get(TRACE_SUPPRESS_HEADER.lower()) == "true"
        ):
            suppress_token = bind_trace_suppressed()
            try:
                await self.app(scope, receive, send)
            finally:
                reset_trace_suppressed(suppress_token)
            return

        traceparent_id, traceparent_span = parse_traceparent(
            headers.get(TRACEPARENT_HEADER.lower())
        )
        trace_id = (
            parse_uuid(headers.get(TRACE_ID_HEADER.lower()))
            or traceparent_id
            or uuid4()
        )
        parent_span_id = (
            parse_uuid(headers.get(PARENT_SPAN_ID_HEADER.lower()))
            or traceparent_span
        )
        span_id = uuid4()
        context_token = bind_trace_context(
            TraceContext(trace_id=trace_id, span_id=span_id)
        )
        capture_token = bind_trace_capture(self.service)
        started_at = datetime.now(UTC)
        started_ns = time.perf_counter_ns()
        request_body = bytearray()
        response_body = bytearray()
        response_headers: dict[str, str] = {}
        status_code = 500
        error_message: str | None = None

        async def traced_receive() -> Message:
            message = await receive()
            if message["type"] == "http.request":
                request_body.extend(message.get("body", b""))
            return message

        async def traced_send(message: Message) -> None:
            nonlocal status_code, response_headers
            if message["type"] == "http.response.start":
                status_code = int(message["status"])
                raw_headers = list(message.get("headers", []))
                raw_headers.append(
                    (TRACE_ID_HEADER.lower().encode(), str(trace_id).encode())
                )
                message["headers"] = raw_headers
                response_headers = {
                    key.decode("latin-1").lower(): value.decode("latin-1")
                    for key, value in raw_headers
                }
            elif message["type"] == "http.response.body":
                response_body.extend(message.get("body", b""))
            await send(message)

        try:
            await self.app(scope, traced_receive, traced_send)
        except Exception as exc:
            error_message = f"{type(exc).__name__}: {exc}"
            raise
        finally:
            ended_at = datetime.now(UTC)
            duration_ms = max(0, (time.perf_counter_ns() - started_ns) // 1_000_000)
            status = self._status(status_code, error_message)
            batch = self._build_batch(
                scope=scope,
                headers=headers,
                trace_id=trace_id,
                parent_span_id=parent_span_id,
                span_id=span_id,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
                status_code=status_code,
                status=status,
                error_message=error_message,
                request_body=bytes(request_body),
                response_body=bytes(response_body),
                response_headers=response_headers,
            )
            if not self._is_empty_message_poll(
                path=str(scope.get("path", "")),
                response_body=bytes(response_body),
                response_content_type=response_headers.get("content-type", ""),
            ):
                try:
                    await self.sink(batch)
                except Exception:
                    pass
            reset_trace_capture(capture_token)
            reset_trace_context(context_token)

    def _is_excluded(self, path: str) -> bool:
        return path.startswith(self.ingest_path_prefix) or any(
            path.startswith(prefix) for prefix in self.excluded_path_prefixes
        )

    @staticmethod
    def _is_empty_message_poll(
        *,
        path: str,
        response_body: bytes,
        response_content_type: str,
    ) -> bool:
        """空 MQ 长轮询不产生日志，实际领取到消息时仍完整记录。"""
        if path != MQ_OUTBOUND_CLAIM_PATH or "application/json" not in (
            response_content_type.lower()
        ):
            return False
        try:
            body = json.loads(response_body)
        except (UnicodeDecodeError, json.JSONDecodeError):
            return False
        return isinstance(body, dict) and body.get("data") is None

    @staticmethod
    def _headers(scope: Scope) -> dict[str, str]:
        return {
            key.decode("latin-1").lower(): value.decode("latin-1")
            for key, value in scope.get("headers", [])
        }

    @staticmethod
    def _status(status_code: int, error_message: str | None) -> TraceStatus:
        if status_code in {408, 504}:
            return TraceStatus.TIMEOUT
        if error_message is not None or status_code >= 500:
            return TraceStatus.ERROR
        if status_code in {401, 403}:
            return TraceStatus.DENIED
        if status_code >= 400:
            return TraceStatus.ERROR
        return TraceStatus.SUCCESS

    def _build_batch(
        self,
        *,
        scope: Scope,
        headers: dict[str, str],
        trace_id: UUID,
        parent_span_id: UUID | None,
        span_id: UUID,
        started_at: datetime,
        ended_at: datetime,
        duration_ms: int,
        status_code: int,
        status: TraceStatus,
        error_message: str | None,
        request_body: bytes,
        response_body: bytes,
        response_headers: dict[str, str],
    ) -> TraceBatch:
        method = str(scope.get("method", ""))
        path = str(scope.get("path", ""))
        query_string = bytes(scope.get("query_string", b"")).decode(
            "utf-8",
            errors="replace",
        )
        request_content_type = headers.get("content-type", "")
        response_content_type = response_headers.get("content-type", "")
        trigger = (
            TraceTrigger.INTERNAL_HTTP
            if "x-api-key" in headers
            else TraceTrigger.FRONTEND_HTTP
        )
        attributes: dict[str, Any] = {
            "http.method": method,
            "http.path": path,
            "http.query": query_string,
            "http.status_code": status_code,
            "request.headers": sanitize_headers(headers),
            "response.headers": sanitize_headers(response_headers),
        }
        span = TraceSpan(
            span_id=span_id,
            trace_id=trace_id,
            parent_span_id=parent_span_id,
            service=self.service,
            kind=SpanKind.SERVER,
            operation=f"{method} {path}",
            status=status,
            started_at=started_at,
            ended_at=ended_at,
            duration_ms=duration_ms,
            attributes=attributes,
            error_message=error_message,
        )
        event = TraceEvent(
            trace_id=trace_id,
            span_id=span_id,
            service=self.service,
            event_type=TraceEventType.HTTP_REQUEST,
            level=(
                TraceLevel.ERROR
                if status is not TraceStatus.SUCCESS
                else TraceLevel.INFO
            ),
            name=f"{method} {path}",
            occurred_at=ended_at,
            attributes={"status_code": status_code},
        )
        payloads: list[TracePayload] = []
        if request_body:
            payloads.append(
                TracePayload(
                    trace_id=trace_id,
                    span_id=span_id,
                    service=self.service,
                    payload_type=TracePayloadType.HTTP_REQUEST_BODY,
                    content_type=request_content_type or "application/octet-stream",
                    content=decode_body(request_body, request_content_type),
                    size_bytes=len(request_body),
                    created_at=started_at,
                )
            )
        if response_body:
            payloads.append(
                TracePayload(
                    trace_id=trace_id,
                    span_id=span_id,
                    service=self.service,
                    payload_type=TracePayloadType.HTTP_RESPONSE_BODY,
                    content_type=response_content_type or "application/octet-stream",
                    content=decode_body(response_body, response_content_type),
                    size_bytes=len(response_body),
                    created_at=ended_at,
                )
            )
        return TraceBatch(
            trace=TraceRecord(
                trace_id=trace_id,
                trigger=trigger,
                name=f"{method} {path}",
                status=status,
                started_at=started_at,
                ended_at=ended_at,
                duration_ms=duration_ms,
                root_service=self.service,
                http_method=method,
                http_path=path,
                http_status=status_code,
                error_message=error_message,
            ),
            spans=[span],
            events=[event, *captured_events()],
            payloads=payloads,
        )
