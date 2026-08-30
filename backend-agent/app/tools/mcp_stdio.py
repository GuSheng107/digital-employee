from __future__ import annotations

import asyncio
import json
import os
import re
from contextlib import AbstractAsyncContextManager
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

from app.core.contracts import ErrorCode, RuntimeError, ToolResult, ToolSpec
from app.core.definitions import MCPServerDefinition


def _field(value: object, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


class MCPStdioSession(AbstractAsyncContextManager["MCPStdioSession"]):
    def __init__(self, server: MCPServerDefinition, result_max_chars: int) -> None:
        self.server = server
        self.result_max_chars = result_max_chars
        self._transport: Any = None
        self._session_context: Any = None
        self.session: ClientSession | None = None
        self.tools: list[ToolSpec] = []
        self._remote_names: dict[str, str] = {}

    async def __aenter__(self) -> "MCPStdioSession":
        environment = {**os.environ, **self.server.env}
        parameters = StdioServerParameters(command=self.server.command, args=self.server.args, env=environment)
        try:
            self._transport = stdio_client(parameters)
            # anyio cancel scopes must be entered and exited by the same Task.
            # Do not wrap context-manager entry in wait_for(), which creates another Task.
            read_stream, write_stream = await self._transport.__aenter__()
            self._session_context = ClientSession(read_stream, write_stream)
            self.session = await self._session_context.__aenter__()
            await asyncio.wait_for(self.session.initialize(), self.server.timeout_seconds)
            listed = await asyncio.wait_for(self.session.list_tools(), self.server.timeout_seconds)
            self.tools = [self._to_spec(tool) for tool in _field(listed, "tools", []) or []]
            return self
        except Exception as exc:
            await self._close()
            raise RuntimeError(ErrorCode.TOOL_EXECUTION_FAILED, f"MCP 服务器 [{self.server.id}] 启动或发现工具失败。") from exc

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self._close()

    async def invoke(self, tool_name: str, arguments: dict[str, Any], tool_call_id: str) -> ToolResult:
        if self.session is None:
            raise RuntimeError(ErrorCode.TOOL_EXECUTION_FAILED, "MCP 会话尚未建立。")
        local_name = self._remote_names.get(tool_name, "")
        if not any(tool.name == tool_name for tool in self.tools):
            return ToolResult(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                status="error",
                content="该工具未被当前 Agent 授权。",
                error_code=ErrorCode.TOOL_NOT_ALLOWED,
            )
        try:
            response = await asyncio.wait_for(
                self.session.call_tool(local_name, arguments=arguments),
                self.server.timeout_seconds,
            )
            raw_content = _field(response, "content", []) or []
            text = "\n".join(self._content_to_text(item) for item in raw_content).strip()
            structured = _field(response, "structuredContent")
            is_error = bool(_field(response, "isError", False))
            return ToolResult(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                status="error" if is_error else "success",
                content=self._truncate(text or "工具未返回文本。"),
                structured_data=structured if isinstance(structured, (dict, list)) else None,
                error_code=ErrorCode.TOOL_EXECUTION_FAILED if is_error else None,
            )
        except asyncio.TimeoutError:
            return ToolResult(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                status="error",
                content="工具调用超时。",
                error_code=ErrorCode.TOOL_TIMEOUT,
            )
        except Exception:
            return ToolResult(
                tool_call_id=tool_call_id,
                tool_name=tool_name,
                status="error",
                content="工具调用失败。",
                error_code=ErrorCode.TOOL_EXECUTION_FAILED,
            )

    def _to_spec(self, tool: object) -> ToolSpec:
        name = str(_field(tool, "name", "")).strip()
        if not name:
            raise RuntimeError(ErrorCode.TOOL_EXECUTION_FAILED, f"MCP 服务器 [{self.server.id}] 返回了无名称工具。")
        provider_name = self._safe_tool_name("mcp", self.server.id, name)
        self._remote_names[provider_name] = name
        return ToolSpec(
            name=provider_name,
            description=str(_field(tool, "description", "") or ""),
            input_schema=dict(_field(tool, "inputSchema", {}) or {}),
            source="mcp",
            source_id=self.server.id,
            timeout_seconds=self.server.timeout_seconds,
        )

    @staticmethod
    def _safe_tool_name(*parts: str) -> str:
        value = "_".join(parts)
        return re.sub(r"[^a-zA-Z0-9_-]", "_", value)[:64]

    @staticmethod
    def _content_to_text(item: object) -> str:
        text = _field(item, "text")
        if text is not None:
            return str(text)
        if isinstance(item, dict):
            return json.dumps(item, ensure_ascii=False)
        return str(item)

    def _truncate(self, value: str) -> str:
        if len(value) <= self.result_max_chars:
            return value
        return value[: self.result_max_chars] + "\n[工具结果已截断]"

    async def _close(self) -> None:
        if self._session_context is not None:
            await self._session_context.__aexit__(None, None, None)
            self._session_context = None
        if self._transport is not None:
            await self._transport.__aexit__(None, None, None)
            self._transport = None
        self.session = None
