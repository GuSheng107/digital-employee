from __future__ import annotations

import asyncio
from collections.abc import Awaitable, Callable
from typing import Any

from app.core.contracts import ErrorCode, ToolResult

SkillHandler = Callable[[dict[str, Any]], Awaitable[dict[str, Any]]]


async def format_weather_observation(arguments: dict[str, Any]) -> dict[str, Any]:
    """A safe built-in example. Skills may only name handlers from this registry."""
    city = str(arguments["city"])
    weather = str(arguments["weather"])
    temperature = float(arguments["temperature_c"])
    return {"summary": f"{city}：{weather}，{temperature:g} 摄氏度。"}


HANDLERS: dict[str, SkillHandler] = {"format_weather_observation": format_weather_observation}


class SkillToolExecutor:
    def __init__(self, handlers: dict[str, SkillHandler] | None = None) -> None:
        self.handlers = handlers or HANDLERS

    async def execute(
        self,
        skill_id: str,
        local_tool_name: str,
        handler_name: str,
        arguments: dict[str, Any],
        tool_call_id: str,
        timeout_seconds: float,
    ) -> ToolResult:
        handler = self.handlers.get(handler_name)
        qualified_name = f"skill_{skill_id}_{local_tool_name}"
        if handler is None:
            return ToolResult(
                tool_call_id=tool_call_id,
                tool_name=qualified_name,
                status="error",
                content="该 Skill 工具未注册受信任处理器。",
                error_code=ErrorCode.TOOL_NOT_ALLOWED,
            )
        try:
            data = await asyncio.wait_for(handler(arguments), timeout=timeout_seconds)
            return ToolResult(
                tool_call_id=tool_call_id,
                tool_name=qualified_name,
                status="success",
                content=str(data.get("summary") or data),
                structured_data=data,
            )
        except asyncio.TimeoutError:
            return ToolResult(tool_call_id=tool_call_id, tool_name=qualified_name, status="error", content="Skill 工具调用超时。", error_code=ErrorCode.TOOL_TIMEOUT)
        except Exception:
            return ToolResult(tool_call_id=tool_call_id, tool_name=qualified_name, status="error", content="Skill 工具调用失败。", error_code=ErrorCode.TOOL_EXECUTION_FAILED)
