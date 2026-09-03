from __future__ import annotations

from types import SimpleNamespace

from app.core.definitions import ModelProfile
from app.infrastructure.model_gateway import LiteLLMModelGateway


def test_provider_response_accepts_attribute_objects_without_model_dump() -> None:
    response = SimpleNamespace(
        id="request-1",
        choices=[
            SimpleNamespace(
                finish_reason="tool_calls",
                message=SimpleNamespace(
                    content="",
                    tool_calls=[
                        SimpleNamespace(
                            id="call-1",
                            function=SimpleNamespace(name="mcp.weather.get_weather", arguments='{"city":"北京"}'),
                        )
                    ],
                ),
            )
        ],
        usage=SimpleNamespace(prompt_tokens=10, completion_tokens=5, total_tokens=15),
    )

    normalized = LiteLLMModelGateway._response_from_provider(response)

    assert normalized.provider_request_id == "request-1"
    assert normalized.tool_calls[0].arguments == {"city": "北京"}
    assert normalized.usage["total_tokens"] == 15


def test_openai_compatible_proxy_gets_explicit_provider_prefix() -> None:
    gateway = LiteLLMModelGateway()
    assert gateway._resolve_model_name(ModelProfile(model="gpt-5.6-terra", api_base="https://example.test/v1")) == "openai/gpt-5.6-terra"
    assert gateway._resolve_model_name(ModelProfile(model="deepseek/deepseek-chat", api_base="https://example.test/v1")) == "deepseek/deepseek-chat"
