from __future__ import annotations

"""LLM 模型构建模块，支持多种提供商（OpenAI、DashScope、Claude、Gemini 等）。"""

import importlib
import inspect
from typing import Any

from app.config_loader import AgentProviderSettings, Settings
from app.exceptions import ConfigError, DependencyError
from app.logger import get_logger

logger = get_logger("agent_runtime.models")


LANGCHAIN_CHAT_CLASSES: dict[str, tuple[str, str]] = {
    "openai": ("langchain_openai", "ChatOpenAI"),
    "dashscope": ("langchain_community.chat_models.tongyi", "ChatTongyi"),
    "zhipu": ("langchain_community.chat_models", "ChatZhipuAI"),
    "minimax": ("langchain_community.chat_models", "MiniMaxChat"),
    "moonshot": ("langchain_openai", "ChatOpenAI"),
    "deepseek": ("langchain_openai", "ChatOpenAI"),
    "claude": ("langchain_anthropic", "ChatAnthropic"),
    "gemini": ("langchain_google_genai", "ChatGoogleGenerativeAI"),
    "openai_compatible": ("langchain_openai", "ChatOpenAI"),
}

_DASHSCOPE_BLOCKED_MODEL_KWARGS = {
    "base_address",
    "base_url",
    "url",
}

# DashScope 特有参数列表，这些参数不应该传递给其他提供商
_DASHSCOPE_SPECIFIC_PARAMS = {
    "enable_search",
    "search_options",
    "enable_thinking",
    "request_timeout",
}

_DASHSCOPE_MULTIMODAL_MODEL_PREFIXES = (
    "qwen3.6-",
    "qwen3.5-",
)


def _fix_dashscope_client(llm: Any, model_name: str) -> None:
    import dashscope

    if not hasattr(llm, "client"):
        return
    current_client = llm.client
    if current_client is dashscope.MultiModalConversation:
        return
    if any(model_name.startswith(p) for p in _DASHSCOPE_MULTIMODAL_MODEL_PREFIXES):
        logger.debug(
            "DashScope 模型 %s 需要 MultiModalConversation，已修正 client。",
            model_name,
        )
        llm.client = dashscope.MultiModalConversation


def build_chat_model(settings: Settings, *, no_retry: bool = False) -> Any:
    """根据配置构建 LLM 聊天模型实例，自动选择对应的 LangChain Chat 类并注入提供商参数。"""
    provider = settings.agent.providers.get(settings.agent.provider)
    if provider is None:
        raise ConfigError(f"未知的 Agent 提供商: {settings.agent.provider}")
    if not provider.api_key.strip():
        raise ConfigError(f"提供商 {settings.agent.provider} 需要 API 密钥。")

    provider_type = provider.type.strip().lower()
    entry = LANGCHAIN_CHAT_CLASSES.get(provider_type)
    if entry is None:
        raise ConfigError(f"不支持的 Agent 提供商类型: {provider.type}")

    module_path, class_name = entry
    try:
        mod = importlib.import_module(module_path)
    except ImportError as exc:
        raise DependencyError(f"{module_path} 未安装。") from exc

    ChatClass = getattr(mod, class_name)
    kwargs = _build_kwargs(provider, ChatClass, max_reasoning_chars=settings.agent.max_reasoning_chars, no_retry=no_retry)
    llm = ChatClass(**kwargs)

    if provider_type == "dashscope":
        _fix_dashscope_client(llm, provider.model.strip())

    return llm


def _build_kwargs(provider: AgentProviderSettings, ChatClass: type, *, max_reasoning_chars: int = 0, no_retry: bool = False) -> dict[str, Any]:
    """根据提供商配置构建 LangChain Chat 类的初始化参数字典。"""
    kwargs: dict[str, Any] = {
        "temperature": provider.temperature,
        "timeout": provider.timeout_seconds,
        "max_retries": 0 if no_retry else provider.max_retries,
        "stream_usage": True,
    }

    if provider.type in ("openai", "openai_compatible"):
        kwargs["model"] = provider.model
        kwargs["api_key"] = provider.api_key
        if provider.type == "openai_compatible":
            if not provider.base_url.strip():
                raise ConfigError("OpenAI 兼容提供商需要配置 base_url。")
            kwargs["base_url"] = provider.base_url.strip()
    elif provider.type == "dashscope":
        fields = getattr(ChatClass, "model_fields", {}) or {}

        model_name = provider.model.strip()
        if isinstance(fields, dict) and "model" in fields:
            kwargs["model"] = model_name
        elif isinstance(fields, dict) and "model_name" in fields:
            kwargs["model_name"] = model_name

        if isinstance(fields, dict) and "dashscope_api_key" in fields:
            kwargs["dashscope_api_key"] = provider.api_key
        elif isinstance(fields, dict) and "api_key" in fields:
            kwargs["api_key"] = provider.api_key
        
    elif provider.type == "zhipu":
        kwargs["model"] = provider.model.strip()
        kwargs["api_key"] = provider.api_key
    elif provider.type == "minimax":
        kwargs["model"] = provider.model.strip()
        kwargs["api_key"] = provider.api_key
    elif provider.type == "moonshot":
        kwargs["model"] = provider.model.strip()
        kwargs["api_key"] = provider.api_key
        kwargs["base_url"] = provider.base_url.strip() or "https://api.moonshot.cn/v1"
    elif provider.type == "deepseek":
        kwargs["model"] = provider.model.strip()
        kwargs["api_key"] = provider.api_key
        kwargs["base_url"] = provider.base_url.strip() or "https://api.deepseek.com"
    elif provider.type == "claude":
        kwargs["model"] = provider.model.strip()
        kwargs["anthropic_api_key"] = provider.api_key
        if provider.base_url.strip():
            kwargs["anthropic_api_url"] = provider.base_url.strip()
    elif provider.type == "gemini":
        kwargs["model"] = provider.model.strip()
        kwargs["google_api_key"] = provider.api_key

    model_kwargs = dict(provider.model_kwargs or {})
    if provider.type == "dashscope":
        model_kwargs = _sanitize_dashscope_model_kwargs(model_kwargs, provider.label)
        if "request_timeout" not in model_kwargs:
            model_kwargs["request_timeout"] = provider.timeout_seconds
        if "reasoning_effort" in model_kwargs:
            re_value = model_kwargs.pop("reasoning_effort")
            if re_value is None or re_value == "":
                model_kwargs["enable_thinking"] = False
            else:
                model_kwargs["enable_thinking"] = True
    
    # 如果显式设置了空的 reasoning_effort，移除它以关闭思考模式
    if (
        "reasoning_effort" in model_kwargs 
        and (model_kwargs["reasoning_effort"] is None or model_kwargs["reasoning_effort"] == "")
    ):
        model_kwargs.pop("reasoning_effort", None)

    _drop_model_token_budget_overrides(model_kwargs, provider.label)
    _inject_max_tokens_budget(kwargs, model_kwargs, ChatClass, provider.type, max_reasoning_chars)

    _promote_explicit_chat_kwargs(kwargs, model_kwargs, ChatClass, provider.type)

    if model_kwargs:
        kwargs["model_kwargs"] = model_kwargs

    if provider.type == "openai" and provider.built_in_tools:
        kwargs["output_version"] = "responses/v1"

    return kwargs


_MAX_TOKENS_PARAM_NAMES = ("max_tokens", "max_output_tokens", "max_completion_tokens")


def _inject_max_tokens_budget(
    kwargs: dict[str, Any],
    model_kwargs: dict[str, Any],
    ChatClass: type,
    provider_type: str,
    max_reasoning_chars: int,
) -> None:
    if max_reasoning_chars <= 0:
        return
    for key in _MAX_TOKENS_PARAM_NAMES:
        if key in kwargs or key in model_kwargs:
            return
    fields = getattr(ChatClass, "model_fields", {}) or {}
    if not isinstance(fields, dict):
        return
    token_budget = max_reasoning_chars // 2
    token_budget = max(token_budget, 256)
    for key in _MAX_TOKENS_PARAM_NAMES:
        if key in fields:
            model_kwargs[key] = token_budget
            return


def _drop_model_token_budget_overrides(model_kwargs: dict[str, Any], provider_label: str) -> None:
    removed: list[str] = []
    for key in _MAX_TOKENS_PARAM_NAMES:
        if key in model_kwargs:
            removed.append(key)
            model_kwargs.pop(key, None)
    if removed:
        logger.warning(
            "Agent %s 的自定义参数包含模型输出 token 上限字段 %s，已忽略；该上限统一由系统设置管理。",
            provider_label,
            ", ".join(removed),
        )


def _sanitize_dashscope_model_kwargs(
    model_kwargs: dict[str, Any],
    provider_label: str,
) -> dict[str, Any]:
    sanitized = dict(model_kwargs)
    removed = []
    for key in list(sanitized.keys()):
        if key in _DASHSCOPE_BLOCKED_MODEL_KWARGS:
            removed.append(key)
            sanitized.pop(key, None)
    if removed:
        logger.warning(
            "Agent %s 的 DashScope 自定义参数包含会覆盖底层请求地址的字段 %s，已忽略。",
            provider_label,
            ", ".join(sorted(removed)),
        )
    return sanitized


def _promote_explicit_chat_kwargs(
    kwargs: dict[str, Any],
    model_kwargs: dict[str, Any],
    ChatClass: type,
    provider_type: str,
) -> None:
    fields = getattr(ChatClass, "model_fields", {}) or {}
    if not isinstance(fields, dict):
        return
    
    # 对于非 DashScope 提供商，先过滤掉 DashScope 特有参数
    if provider_type != "dashscope":
        _filter_dashscope_specific_params(model_kwargs)
    
    for key in list(model_kwargs.keys()):
        if key in kwargs:
            continue
        if key in fields:
            kwargs[key] = model_kwargs.pop(key)


def _filter_dashscope_specific_params(model_kwargs: dict[str, Any]) -> None:
    """从 model_kwargs 中移除 DashScope 特有参数，避免传递给其他提供商."""
    removed = []
    for key in list(model_kwargs.keys()):
        if key in _DASHSCOPE_SPECIFIC_PARAMS:
            removed.append(key)
            model_kwargs.pop(key, None)
    if removed:
        logger.warning(
            "非 DashScope 提供商的自定义参数包含 DashScope 特有字段 %s，已忽略。",
            ", ".join(sorted(removed)),
        )


def _supports_explicit_chat_kw(ChatClass: type, key: str) -> bool:
    fields = getattr(ChatClass, "model_fields", {}) or {}
    return isinstance(fields, dict) and key in fields
