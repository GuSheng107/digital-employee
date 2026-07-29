"""请求内统一业务事件采集与类级装饰器。"""

from __future__ import annotations

import inspect
import time
from contextvars import ContextVar, Token
from dataclasses import dataclass, field
from functools import wraps
from typing import Any, TypeVar

from observability.context import current_trace_context, is_trace_suppressed
from observability.enums import TraceEventType, TraceLevel, TraceService
from observability.sanitize import sanitize_value
from observability.schemas import TraceEvent

T = TypeVar("T", bound=type)


@dataclass(slots=True)
class TraceCapture:
    """一次入口请求内追加的业务事件。"""

    service: TraceService
    events: list[TraceEvent] = field(default_factory=list)


_trace_capture: ContextVar[TraceCapture | None] = ContextVar(
    "trace_capture",
    default=None,
)


def bind_trace_capture(service: TraceService) -> Token[TraceCapture | None]:
    """为入口请求绑定可跨线程上下文传播的可变事件容器。"""
    return _trace_capture.set(TraceCapture(service=service))


def reset_trace_capture(token: Token[TraceCapture | None]) -> None:
    """恢复入口前的事件容器。"""
    _trace_capture.reset(token)


def captured_events() -> list[TraceEvent]:
    """读取当前入口已采集事件的副本。"""
    capture = _trace_capture.get()
    return list(capture.events) if capture is not None else []


def record_trace_event(
    event_type: TraceEventType,
    name: str,
    *,
    level: TraceLevel = TraceLevel.INFO,
    attributes: dict[str, Any] | None = None,
) -> None:
    """向当前入口追加结构化事件；无上下文或抑制时安全忽略。"""
    if is_trace_suppressed():
        return
    capture = _trace_capture.get()
    context = current_trace_context()
    if capture is None or context is None:
        return
    capture.events.append(
        TraceEvent(
            trace_id=context.trace_id,
            span_id=context.span_id,
            service=capture.service,
            event_type=event_type,
            level=level,
            name=name,
            attributes=sanitize_value(attributes or {}),
        )
    )


def traced_class(event_type: TraceEventType) -> Any:
    """装饰类的公开方法，统一记录业务或基础设施操作结果与耗时。"""

    def decorate(cls: T) -> T:
        marker = f"__observability_{event_type.value}_instrumented__"
        if getattr(cls, marker, False):
            return cls
        for method_name, method in list(vars(cls).items()):
            if method_name.startswith("_") or not inspect.isfunction(method):
                continue
            qualified_name = f"{cls.__name__}.{method_name}"
            if inspect.iscoroutinefunction(method):
                setattr(
                    cls,
                    method_name,
                    _wrap_async(method, qualified_name, event_type),
                )
            else:
                setattr(
                    cls,
                    method_name,
                    _wrap_sync(method, qualified_name, event_type),
                )
        setattr(cls, marker, True)
        return cls

    return decorate


def _event_attributes(
    *,
    duration_ms: int,
    success: bool,
    exception: Exception | None = None,
) -> dict[str, Any]:
    attributes: dict[str, Any] = {
        "duration_ms": duration_ms,
        "success": success,
    }
    if exception is not None:
        attributes["exception_type"] = type(exception).__name__
        attributes["exception_message"] = str(exception)
    return attributes


def _wrap_sync(method: Any, name: str, event_type: TraceEventType) -> Any:
    @wraps(method)
    def wrapper(*args: Any, **kwargs: Any) -> Any:
        started_ns = time.perf_counter_ns()
        try:
            result = method(*args, **kwargs)
        except Exception as exc:
            record_trace_event(
                event_type,
                name,
                level=TraceLevel.ERROR,
                attributes=_event_attributes(
                    duration_ms=(time.perf_counter_ns() - started_ns) // 1_000_000,
                    success=False,
                    exception=exc,
                ),
            )
            raise
        record_trace_event(
            event_type,
            name,
            attributes=_event_attributes(
                duration_ms=(time.perf_counter_ns() - started_ns) // 1_000_000,
                success=True,
            ),
        )
        return result

    return wrapper


def _wrap_async(method: Any, name: str, event_type: TraceEventType) -> Any:
    @wraps(method)
    async def wrapper(*args: Any, **kwargs: Any) -> Any:
        started_ns = time.perf_counter_ns()
        try:
            result = await method(*args, **kwargs)
        except Exception as exc:
            record_trace_event(
                event_type,
                name,
                level=TraceLevel.ERROR,
                attributes=_event_attributes(
                    duration_ms=(time.perf_counter_ns() - started_ns) // 1_000_000,
                    success=False,
                    exception=exc,
                ),
            )
            raise
        record_trace_event(
            event_type,
            name,
            attributes=_event_attributes(
                duration_ms=(time.perf_counter_ns() - started_ns) // 1_000_000,
                success=True,
            ),
        )
        return result

    return wrapper
