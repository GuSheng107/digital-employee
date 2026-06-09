from __future__ import annotations

"""模型能力标志定义模块，提供不同 AI 模型的能力查询。"""

from enum import Flag, auto
from typing import Any


class ModelCapability(Flag):
    """模型能力标志位，用于描述 AI 模型支持的特性（文本、图像输入、工具调用等）。"""

    TEXT = auto()
    IMAGE_INPUT = auto()
    VIDEO_INPUT = auto()
    DOCUMENT_INPUT = auto()
    AUDIO_INPUT = auto()
    TOOL_CALLING = auto()
    STREAMING = auto()


_T = ModelCapability.TEXT
_I = ModelCapability.IMAGE_INPUT
_V = ModelCapability.VIDEO_INPUT
_D = ModelCapability.DOCUMENT_INPUT
_A = ModelCapability.AUDIO_INPUT
_TC = ModelCapability.TOOL_CALLING
_S = ModelCapability.STREAMING

MODEL_CAPABILITIES: dict[str, ModelCapability] = {
    # OpenAI official model pages
    "gpt-5.5": _T | _I | _D | _TC | _S,
    "gpt-5.4": _T | _I | _D | _TC | _S,
    "gpt-5.4-mini": _T | _I | _D | _TC | _S,
    "gpt-5.4-nano": _T | _I | _D | _TC | _S,
    "gpt-5": _T | _I | _D | _TC | _S,
    "gpt-5-mini": _T | _I | _D | _TC | _S,
    "gpt-4.1": _T | _I | _D | _TC | _S,
    "gpt-4.1-mini": _T | _I | _D | _TC | _S,
    "gpt-4.1-nano": _T | _I | _D | _TC | _S,
    "gpt-4o": _T | _I | _D | _TC | _S,
    "gpt-4o-mini": _T | _I | _D | _TC | _S,
    "o4-mini": _T | _I | _D | _TC | _S,
    "o3": _T | _I | _D | _TC | _S,
    "o3-mini": _T | _TC | _S,
    "o1": _T | _I | _D | _TC,
    "deepseek-v4-pro": _T | _TC | _S,
    "deepseek-v4-flash": _T | _TC | _S,
    "deepseek-chat": _T | _TC | _S,
    "deepseek-reasoner": _T | _TC | _S,
    # Qwen3.6 official vision-model docs:
    # https://help.aliyun.com/zh/model-studio/vision-model
    "qwen3.6-max": _T | _I | _V | _TC | _S,
    "qwen3.6-plus": _T | _I | _V | _TC | _S,
    "qwen3.6-flash": _T | _I | _V | _TC | _S,
    "qwen3-max": _T | _TC | _S,
    "qwen3.5-plus": _T | _I | _V | _TC | _S,
    "qwen3.5-flash": _T | _I | _V | _TC | _S,
    "qwen-plus": _T | _TC | _S,
    "qwen-turbo": _T | _TC | _S,
    "qwen-long": _T | _D | _S,
    "qwen3-coder-plus": _T | _TC | _S,
    "qwen-vl-plus": _T | _I | _V | _S,
    "qwen-vl-max": _T | _I | _V | _S,
    "claude-opus-4-7": _T | _I | _D | _TC | _S,
    "claude-opus-4-6": _T | _I | _D | _TC | _S,
    "claude-sonnet-4-6": _T | _I | _D | _TC | _S,
    "claude-opus-4-5": _T | _I | _D | _TC | _S,
    "claude-sonnet-4-5": _T | _I | _D | _TC | _S,
    "claude-haiku-4-5": _T | _I | _D | _TC | _S,
    "claude-3-5-sonnet": _T | _I | _D | _TC | _S,
    "claude-3-opus": _T | _I | _D | _TC | _S,
    "claude-3-haiku": _T | _I | _D | _TC | _S,
    "gemini-3.1-pro": _T | _I | _V | _A | _D | _TC | _S,
    "gemini-3-pro": _T | _I | _V | _A | _D | _TC | _S,
    "gemini-3-flash": _T | _I | _V | _A | _D | _TC | _S,
    "gemini-2.5-pro": _T | _I | _V | _A | _D | _TC | _S,
    "gemini-2.5-flash": _T | _I | _V | _A | _D | _TC | _S,
    "gemini-2.0-flash": _T | _I | _V | _A | _D | _TC | _S,
    # GLM-5 / GLM-5.1 official text-model docs:
    # https://docs.bigmodel.cn/cn/guide/models/text/glm-5
    # https://docs.bigmodel.cn/cn/guide/models/text/glm-5.1
    "glm-5.1": _T | _TC | _S,
    "glm-5": _T | _TC | _S,
    "glm-5-turbo": _T | _TC | _S,
    "glm-5v-turbo": _T | _I | _TC | _S,
    "glm-4.6v": _T | _I | _TC | _S,
    "glm-4.7-flash": _T | _I | _D | _TC | _S,
    "minimax-m2.7": _T | _I | _TC | _S,
    "minimax-m2.7-highspeed": _T | _I | _TC | _S,
    "minimax-m2.5": _T | _TC | _S,
    "minimax-m2.5-highspeed": _T | _TC | _S,
    "minimax-m2.1": _T | _TC | _S,
    "minimax-m2": _T | _TC | _S,
    "kimi-k2.6": _T | _TC | _S,
    "kimi-k2.5": _T | _I | _TC | _S,
    "moonshot-v1": _T | _TC | _S,
    "moonshot-v1-8k-vision-preview": _T | _I | _TC | _S,
    "moonshot-v1-32k-vision-preview": _T | _I | _TC | _S,
    "moonshot-v1-128k-vision-preview": _T | _I | _TC | _S,
}

_PROVIDER_DEFAULTS: dict[str, ModelCapability] = {
    "openai": _T | _S,
    "openai_compatible": _T | _S,
    "dashscope": _T | _S,
    "zhipu": _T | _S,
    "minimax": _T | _S,
    "moonshot": _T | _S,
    "deepseek": _T | _TC | _S,
    # Provider-level defaults stay conservative.
    "claude": _T | _TC | _S,
    "gemini": _T | _TC | _S,
}


def get_model_capabilities(
    model_name: str,
    provider_type: str,
    user_override: list[str] | None = None,
) -> ModelCapability:
    """根据模型名称和提供商类型查询模型能力，支持用户自定义覆盖。"""
    if user_override:
        result = ModelCapability(0)
        for cap_name in user_override:
            try:
                result |= ModelCapability[cap_name.upper()]
            except KeyError:
                pass
        return result if result else ModelCapability.TEXT

    if model_name in MODEL_CAPABILITIES:
        return MODEL_CAPABILITIES[model_name]

    for prefix, caps in MODEL_CAPABILITIES.items():
        if model_name.startswith(prefix):
            return caps

    return _PROVIDER_DEFAULTS.get(provider_type, ModelCapability.TEXT)


def detect_capabilities_api(model_name: str, provider_type: str) -> dict[str, Any]:
    caps = get_model_capabilities(model_name, provider_type)
    return {
        "capabilities": [c.name for c in ModelCapability if c in caps],
        "auto_detected": model_name in MODEL_CAPABILITIES or any(
            model_name.startswith(p) for p in MODEL_CAPABILITIES
        ),
    }
