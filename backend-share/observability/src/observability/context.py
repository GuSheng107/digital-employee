"""基于 ContextVar 的跨异步任务链路上下文。"""

from contextvars import ContextVar, Token
from dataclasses import dataclass
from uuid import UUID, uuid4

TRACE_ID_HEADER = "X-Trace-Id"
PARENT_SPAN_ID_HEADER = "X-Parent-Span-Id"
TRACEPARENT_HEADER = "traceparent"
TRACE_SUPPRESS_HEADER = "X-Trace-Suppress"
TRACEPARENT_VERSION = "00"
TRACEPARENT_FLAGS = "01"


@dataclass(frozen=True, slots=True)
class TraceContext:
    """当前执行上下文中的 trace 与 span 标识。"""

    trace_id: UUID
    span_id: UUID


_trace_context: ContextVar[TraceContext | None] = ContextVar(
    "trace_context",
    default=None,
)
_trace_suppressed: ContextVar[bool] = ContextVar("trace_suppressed", default=False)


def current_trace_context() -> TraceContext | None:
    """读取当前链路上下文。"""
    return _trace_context.get()


def bind_trace_context(context: TraceContext) -> Token[TraceContext | None]:
    """绑定链路上下文并返回可用于恢复的 token。"""
    return _trace_context.set(context)


def reset_trace_context(token: Token[TraceContext | None]) -> None:
    """恢复绑定前的链路上下文。"""
    _trace_context.reset(token)


def is_trace_suppressed() -> bool:
    """判断当前链路是否明确禁止记录。"""
    return _trace_suppressed.get()


def bind_trace_suppressed() -> Token[bool]:
    """绑定禁止记录标记。"""
    return _trace_suppressed.set(True)


def reset_trace_suppressed(token: Token[bool]) -> None:
    """恢复禁止记录标记。"""
    _trace_suppressed.reset(token)


def new_trace_context(
    *,
    trace_id: UUID | None = None,
    span_id: UUID | None = None,
) -> TraceContext:
    """创建链路上下文。"""
    return TraceContext(
        trace_id=trace_id or uuid4(),
        span_id=span_id or uuid4(),
    )


def parse_uuid(value: str | None) -> UUID | None:
    """安全解析 UUID。"""
    if not value:
        return None
    try:
        return UUID(value)
    except ValueError:
        return None


def parse_traceparent(value: str | None) -> tuple[UUID | None, UUID | None]:
    """解析 W3C traceparent，内部 UUID span 使用 128 位自有扩展头补足。"""
    if not value:
        return None, None
    parts = value.split("-")
    if len(parts) != 4:
        return None, None
    try:
        trace_id = UUID(hex=parts[1])
        parent_64 = int(parts[2], 16)
    except (ValueError, OverflowError):
        return None, None
    if trace_id.int == 0 or parent_64 == 0:
        return None, None
    return trace_id, UUID(int=parent_64)


def propagation_headers(context: TraceContext | None = None) -> dict[str, str]:
    """生成服务间 HTTP/MQ 传播头。"""
    active = context or current_trace_context()
    if active is None:
        active = new_trace_context()
    span_hex = active.span_id.hex[-16:]
    headers = {
        TRACE_ID_HEADER: str(active.trace_id),
        PARENT_SPAN_ID_HEADER: str(active.span_id),
        TRACEPARENT_HEADER: (
            f"{TRACEPARENT_VERSION}-{active.trace_id.hex}-{span_hex}-{TRACEPARENT_FLAGS}"
        ),
    }
    if is_trace_suppressed():
        headers[TRACE_SUPPRESS_HEADER] = "true"
    return headers
