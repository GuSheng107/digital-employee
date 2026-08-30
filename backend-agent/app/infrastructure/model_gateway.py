from __future__ import annotations

import json
from collections.abc import AsyncIterator
from typing import Any, Protocol

from app.core.contracts import ChatMessage, ErrorCode, ModelResponse, RuntimeError, ToolCall, ToolSpec
from app.core.definitions import ModelProfile


class ModelGateway(Protocol):
    async def complete(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        profile: ModelProfile,
        tool_choice: str | None = None,
    ) -> ModelResponse: ...


def _field(value: object, name: str, default: Any = None) -> Any:
    if isinstance(value, dict):
        return value.get(name, default)
    return getattr(value, name, default)


def _text(value: Any) -> str:
    if value is None:
        return ""
    if isinstance(value, str):
        return value
    if isinstance(value, list):
        return "".join(str(_field(part, "text", part)) for part in value)
    return str(value)


class LiteLLMModelGateway:
    """The only place where LiteLLM response shapes are allowed into this project."""

    async def complete(
        self,
        messages: list[ChatMessage],
        tools: list[ToolSpec],
        profile: ModelProfile,
        tool_choice: str | None = None,
    ) -> ModelResponse:
        if not profile.api_key:
            raise RuntimeError(ErrorCode.MODEL_UNAVAILABLE, "未配置 MODEL_API_KEY，无法调用模型。")

        try:
            from litellm import acompletion

            request: dict[str, Any] = {
                "model": self._resolve_model_name(profile),
                "messages": [self._message_to_provider(message) for message in messages],
                "api_key": profile.api_key,
                "timeout": profile.timeout_seconds,
                "num_retries": profile.max_retries,
            }
            if profile.api_base:
                request["api_base"] = profile.api_base.rstrip("/")
            if profile.max_output_tokens:
                request["max_tokens"] = profile.max_output_tokens
            if tools:
                request["tools"] = [
                    {
                        "type": "function",
                        "function": {
                            "name": tool.name,
                            "description": tool.description,
                            "parameters": tool.input_schema,
                        },
                    }
                    for tool in tools
                ]
            if tool_choice:
                request["tool_choice"] = {"type": "function", "function": {"name": tool_choice}}

            response = await acompletion(**request)
            return self._response_from_provider(response)
        except RuntimeError:
            raise
        except Exception as exc:
            detail = str(exc).replace(profile.api_key or "", "<redacted>").strip()
            raise RuntimeError(ErrorCode.MODEL_UNAVAILABLE, f"模型调用失败：{type(exc).__name__}: {detail[:400]}") from exc

    async def stream(
        self,
        messages: list[ChatMessage],
        profile: ModelProfile,
    ) -> AsyncIterator[str]:
        """Text-only stream for future no-tool fast paths; tool loops use complete()."""
        if not profile.api_key:
            raise RuntimeError(ErrorCode.MODEL_UNAVAILABLE, "未配置 MODEL_API_KEY，无法调用模型。")
        try:
            from litellm import acompletion

            request: dict[str, Any] = {
                "model": self._resolve_model_name(profile),
                "messages": [self._message_to_provider(message) for message in messages],
                "api_key": profile.api_key,
                "timeout": profile.timeout_seconds,
                "stream": True,
            }
            if profile.api_base:
                request["api_base"] = profile.api_base.rstrip("/")
            stream = await acompletion(**request)
            async for chunk in stream:
                choices = _field(chunk, "choices", []) or []
                if choices:
                    delta = _field(choices[0], "delta", {})
                    text = _text(_field(delta, "content", ""))
                    if text:
                        yield text
        except RuntimeError:
            raise
        except Exception as exc:
            detail = str(exc).replace(profile.api_key or "", "<redacted>").strip()
            raise RuntimeError(ErrorCode.MODEL_UNAVAILABLE, f"模型流式调用失败：{type(exc).__name__}: {detail[:400]}") from exc

    @staticmethod
    def _resolve_model_name(profile: ModelProfile) -> str:
        """Make OpenAI-compatible routing explicit for arbitrary proxy model names."""
        model = profile.model.strip()
        if profile.api_base and "/" not in model:
            return f"openai/{model}"
        return model

    @staticmethod
    def _message_to_provider(message: ChatMessage) -> dict[str, Any]:
        payload: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.tool_call_id:
            payload["tool_call_id"] = message.tool_call_id
        if message.tool_calls:
            payload["tool_calls"] = [
                {
                    "id": call.id,
                    "type": "function",
                    "function": {"name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False)},
                }
                for call in message.tool_calls
            ]
        return payload

    @staticmethod
    def _response_from_provider(response: object) -> ModelResponse:
        choices = _field(response, "choices", []) or []
        if not choices:
            raise RuntimeError(ErrorCode.MODEL_UNAVAILABLE, "模型响应没有 choices。")
        choice = choices[0]
        message = _field(choice, "message", {})
        tool_calls: list[ToolCall] = []
        for call in _field(message, "tool_calls", []) or []:
            function = _field(call, "function", {})
            arguments = _field(function, "arguments", "{}")
            try:
                parsed = json.loads(arguments) if isinstance(arguments, str) else dict(arguments or {})
            except (TypeError, json.JSONDecodeError) as exc:
                raise RuntimeError(ErrorCode.MODEL_UNAVAILABLE, "模型返回了无效的工具参数 JSON。") from exc
            if not isinstance(parsed, dict):
                raise RuntimeError(ErrorCode.MODEL_UNAVAILABLE, "模型工具参数必须是对象。")
            tool_calls.append(
                ToolCall(
                    id=str(_field(call, "id", "")),
                    name=str(_field(function, "name", "")),
                    arguments=parsed,
                )
            )
        usage = _field(response, "usage", {}) or {}
        return ModelResponse(
            content=_text(_field(message, "content", "")),
            tool_calls=tool_calls,
            finish_reason=_field(choice, "finish_reason"),
            usage={
                key: int(value)
                for key, value in {
                    "prompt_tokens": _field(usage, "prompt_tokens", 0),
                    "completion_tokens": _field(usage, "completion_tokens", 0),
                    "total_tokens": _field(usage, "total_tokens", 0),
                }.items()
                if value is not None
            },
            provider_request_id=_field(response, "id"),
        )
