from __future__ import annotations

import asyncio
import logging
from typing import Any


def _is_ignorable_proactor_connection_reset(context: dict[str, Any]) -> bool:
    exc = context.get("exception")
    if not isinstance(exc, ConnectionResetError):
        return False
    if int(getattr(exc, "winerror", 0) or 0) != 10054:
        return False
    handle_text = repr(context.get("handle") or "")
    message_text = str(context.get("message") or "")
    if "_ProactorBasePipeTransport._call_connection_lost" in handle_text:
        return True
    if "_ProactorBasePipeTransport._call_connection_lost" in message_text:
        return True
    return bool(context.get("handle")) and "Exception in callback" in message_text


def _is_ignorable_h11_protocol_error(context: dict[str, Any]) -> bool:
    exc = context.get("exception")
    if exc is None:
        return False
    exc_type = type(exc).__name__
    exc_module = type(exc).__module__
    if "h11" in exc_module and "ProtocolError" in exc_type:
        return True
    handle_text = repr(context.get("handle") or "")
    message_text = str(context.get("message") or "")
    if "_ProactorReadPipeTransport._loop_reading" in handle_text:
        return True
    if "h11" in message_text and "ProtocolError" in message_text:
        return True
    return False


def install_asyncio_exception_filter(
    loop: asyncio.AbstractEventLoop,
    *,
    logger: logging.Logger | None = None,
) -> None:
    previous_handler = loop.get_exception_handler()

    def _handler(current_loop: asyncio.AbstractEventLoop, context: dict[str, Any]) -> None:
        if _is_ignorable_proactor_connection_reset(context):
            return
        if _is_ignorable_h11_protocol_error(context):
            return
        if previous_handler is not None:
            previous_handler(current_loop, context)
            return
        current_loop.default_exception_handler(context)

    loop.set_exception_handler(_handler)
