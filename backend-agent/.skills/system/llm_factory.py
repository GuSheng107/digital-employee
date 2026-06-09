"""Shared LLM factory for memory scripts."""
from __future__ import annotations

import importlib
from typing import Any

LANGCHAIN_CHAT_CLASSES: dict[str, tuple[str, str]] = {
    "openai": ("langchain_openai", "ChatOpenAI"),
    "dashscope": ("langchain_openai", "ChatOpenAI"),
    "zhipu": ("langchain_community.chat_models", "ChatZhipuAI"),
    "minimax": ("langchain_community.chat_models", "MiniMaxChat"),
    "moonshot": ("langchain_openai", "ChatOpenAI"),
    "deepseek": ("langchain_openai", "ChatOpenAI"),
    "claude": ("langchain_anthropic", "ChatAnthropic"),
    "gemini": ("langchain_google_genai", "ChatGoogleGenerativeAI"),
    "openai_compatible": ("langchain_openai", "ChatOpenAI"),
}


_DEFAULT_BASE_URLS: dict[str, str] = {
    "moonshot": "https://api.moonshot.cn/v1",
    "deepseek": "https://api.deepseek.com",
    "dashscope": "https://dashscope.aliyuncs.com/compatible-mode/v1",
}


def build_llm(
    provider_type: str,
    model: str,
    api_key: str,
    base_url: str,
    temperature: float = 0,
    max_tokens: int = 16384,
) -> Any:
    entry = LANGCHAIN_CHAT_CLASSES.get(provider_type)
    if entry is None:
        raise ValueError(f"Unsupported provider type: {provider_type}")

    module_path, class_name = entry
    mod = importlib.import_module(module_path)
    cls = getattr(mod, class_name)
    kwargs: dict[str, Any] = {
        "model": model,
        "api_key": api_key,
        "temperature": temperature,
        "max_tokens": max_tokens,
    }
    if provider_type in ("moonshot", "deepseek", "dashscope"):
        kwargs["base_url"] = base_url or _DEFAULT_BASE_URLS.get(provider_type, "")
    elif provider_type in ("openai", "openai_compatible", "claude", "gemini"):
        if base_url:
            kwargs["base_url"] = base_url
    elif provider_type in ("zhipu", "minimax"):
        if base_url:
            kwargs["azure_endpoint"] = base_url
    return cls(**kwargs)
