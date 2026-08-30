from __future__ import annotations

from enum import StrEnum
from typing import Any, Literal

from pydantic import BaseModel, Field


class ErrorCode(StrEnum):
    MODEL_UNAVAILABLE = "model_unavailable"
    TOOL_NOT_ALLOWED = "tool_not_allowed"
    TOOL_INVALID_ARGUMENTS = "tool_invalid_arguments"
    TOOL_TIMEOUT = "tool_timeout"
    TOOL_EXECUTION_FAILED = "tool_execution_failed"
    TOOL_LOOP_LIMIT = "tool_loop_limit"
    RUN_CANCELLED = "run_cancelled"


class RuntimeError(Exception):
    def __init__(self, code: ErrorCode, message: str) -> None:
        super().__init__(message)
        self.code = code
        self.message = message


class ToolCall(BaseModel):
    id: str
    name: str
    arguments: dict[str, Any] = Field(default_factory=dict)


class ChatMessage(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_call_id: str | None = None
    tool_calls: list[ToolCall] = Field(default_factory=list)


class ToolSpec(BaseModel):
    name: str
    description: str = ""
    input_schema: dict[str, Any] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    source: Literal["mcp", "skill"]
    source_id: str
    risk_level: Literal["read", "write"] = "read"
    timeout_seconds: float = 20.0


class ToolResult(BaseModel):
    tool_call_id: str
    tool_name: str
    status: Literal["success", "error"]
    content: str
    structured_data: dict[str, Any] | list[Any] | None = None
    error_code: ErrorCode | None = None


class ModelResponse(BaseModel):
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    finish_reason: str | None = None
    usage: dict[str, int] = Field(default_factory=dict)
    provider_request_id: str | None = None


class RunRequest(BaseModel):
    agent_id: str
    message: str = Field(min_length=1, max_length=20_000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    conversation_id: str | None = Field(default=None, max_length=200)
    request_id: str | None = Field(default=None, max_length=200)


class RunEvent(BaseModel):
    type: str
    run_id: str
    trace_id: str
    data: dict[str, Any] = Field(default_factory=dict)


class RunResult(BaseModel):
    run_id: str
    trace_id: str
    status: Literal["completed", "failed", "cancelled"]
    answer: str = ""
    usage: dict[str, int] = Field(default_factory=dict)
    error_code: ErrorCode | None = None
    error_message: str | None = None

