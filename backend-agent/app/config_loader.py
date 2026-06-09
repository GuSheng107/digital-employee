from __future__ import annotations

"""配置数据类定义与加载验证模块。

定义了所有配置相关的数据类（Settings、AgentSettings、AgentProviderSettings、
WecomBotSettings、RuntimeLimitSettings 等），并提供从 YAML 配置和数据库加载、
填充默认值、验证配置完整性的功能。
"""

from dataclasses import dataclass, field
from typing import Any

from app.exceptions import ConfigError
from app.yaml_config import get_yaml_config


def _cfg(dot_path: str, default: Any = None) -> Any:
    return get_yaml_config().get(dot_path, default)


@dataclass(slots=True)
class AgentProviderSettings:
    """Agent 提供商配置，包含模型类型、API 密钥、请求参数等信息。"""
    label: str = ""
    type: str = "openai_compatible"
    model: str = ""
    base_url: str = ""
    api_key: str = ""
    temperature: float = 0.2
    timeout_seconds: int = 60
    max_retries: int = 1
    model_kwargs: dict[str, Any] = field(default_factory=dict)
    capabilities: list[str] = field(default_factory=list)
    built_in_tools: list[dict[str, Any]] = field(default_factory=list)


@dataclass(slots=True)
class ContextSettings:
    compression_trigger_chars: int = 0
    summary_max_chars: int = 0

    def _fill_defaults(self) -> None:
        if self.compression_trigger_chars <= 0:
            self.compression_trigger_chars = _cfg("agent.context_length_limit")
        if self.summary_max_chars <= 0:
            self.summary_max_chars = _cfg("agent.summary_max_chars")


@dataclass(slots=True)
class MCPSettings:
    enabled: bool = False
    servers: dict[str, Any] = field(default_factory=dict)
    max_tool_event_payload_chars: int = 0
    max_result_chars: int = 0

    def _fill_defaults(self) -> None:
        if self.max_tool_event_payload_chars <= 0:
            self.max_tool_event_payload_chars = _cfg("mcp.max_tool_event_payload_chars")
        if self.max_result_chars <= 0:
            self.max_result_chars = _cfg("mcp.max_result_chars")


@dataclass(slots=True)
class SkillSettings:
    enabled: list[str] = field(default_factory=list)
    max_script_output_chars: int = 0
    max_tool_description_chars: int = 0

    def _fill_defaults(self) -> None:
        if self.max_script_output_chars <= 0:
            self.max_script_output_chars = _cfg("skills.max_script_output_chars")
        if self.max_tool_description_chars <= 0:
            self.max_tool_description_chars = _cfg("skills.max_tool_description_chars")


@dataclass(slots=True)
class AgentSettings:
    """Agent 智能体配置，包含提供商选择、超时限制、上下文参数、MCP 和技能设置等。"""
    auto_reply: bool = False
    provider: str = ""
    timeout_seconds: int = 0
    max_iterations: int = 0
    reply_notice: str = ""
    providers: dict[str, AgentProviderSettings] = field(default_factory=dict)
    mcp: MCPSettings = field(default_factory=MCPSettings)
    skills: SkillSettings = field(default_factory=SkillSettings)
    context: ContextSettings = field(default_factory=ContextSettings)
    max_image_bytes: int = 0
    max_video_bytes: int = 0
    max_audio_bytes: int = 0
    max_file_bytes: int = 0
    max_stream_chunks: int = 0
    max_output_chars: int = 0
    max_reasoning_chars: int = 0
    reasoning_truncation_notice: str = ""
    max_cache_size: int = 0
    truncation_notice: str = ""
    _force_disabled: bool = field(default=False, init=False, repr=False)
    _system_prompt_override: str = field(default="", init=False, repr=False)
    _fallback_text: str = field(default="", init=False, repr=False)

    def _fill_defaults(self) -> None:
        if not self.provider:
            self.provider = _cfg("agent.provider")
        if self.timeout_seconds <= 0:
            self.timeout_seconds = _cfg("agent.timeout_seconds")
        if self.max_iterations <= 0:
            self.max_iterations = _cfg("agent.max_iterations")
        if not self.reply_notice:
            self.reply_notice = _cfg("agent.reply_notice")
        if not self._fallback_text:
            self._fallback_text = _cfg("agent.fallback_text")
        if self.max_image_bytes <= 0:
            self.max_image_bytes = _cfg("agent.max_image_bytes")
        if self.max_video_bytes <= 0:
            self.max_video_bytes = _cfg("agent.max_video_bytes")
        if self.max_audio_bytes <= 0:
            self.max_audio_bytes = _cfg("agent.max_audio_bytes")
        if self.max_file_bytes <= 0:
            self.max_file_bytes = _cfg("agent.max_file_bytes")
        if self.max_stream_chunks <= 0:
            self.max_stream_chunks = _cfg("agent.max_stream_chunks")
        if self.max_output_chars <= 0:
            self.max_output_chars = _cfg("agent.max_output_chars")
        if self.max_reasoning_chars <= 0:
            self.max_reasoning_chars = _cfg("agent.max_reasoning_chars")
        if not self.reasoning_truncation_notice:
            self.reasoning_truncation_notice = _cfg("agent.reasoning_truncation_notice")
        if self.max_cache_size <= 0:
            self.max_cache_size = _cfg("agent.max_cache_size")
        if not self.truncation_notice:
            self.truncation_notice = _cfg("agent.truncation_notice")
        self.context._fill_defaults()
        self.mcp._fill_defaults()
        self.skills._fill_defaults()

    @property
    def enabled(self) -> bool:
        if self._force_disabled:
            return False
        p = self.providers.get(self.provider)
        return bool(p and p.model.strip())

    @enabled.setter
    def enabled(self, value: bool) -> None:
        # 当 value=False 时，设置 _force_disabled=True 以强制禁用智能体
        self._force_disabled = not value

    @property
    def system_prompt(self) -> str:
        return self._system_prompt_override

    @system_prompt.setter
    def system_prompt(self, value: str) -> None:
        self._system_prompt_override = value

    @property
    def fallback_text(self) -> str:
        return self._fallback_text


@dataclass(slots=True)
class LoggingSettings:
    level: str = ""

    def _fill_defaults(self) -> None:
        if not self.level:
            self.level = _cfg("logging.level")
        # 只允许 INFO、WARNING、ERROR，其他转为 INFO
        if self.level not in ("INFO", "WARNING", "ERROR"):
            self.level = "INFO"


@dataclass(slots=True)
class WeComBotSettings:
    """企业微信机器人配置，包含连接模式、Bot 凭证、WebSocket 地址和心跳参数。"""
    mode: str = "long_connection"
    name: str = ""
    bot_id: str = ""
    secret: str = ""
    websocket_url: str = ""
    reconnect_interval_ms: int = 0
    heartbeat_interval_ms: int = 0

    def _fill_defaults(self) -> None:
        if not self.websocket_url:
            self.websocket_url = _cfg("wecom_bot.websocket_url")
        if self.reconnect_interval_ms <= 0:
            self.reconnect_interval_ms = _cfg("wecom_bot.reconnect_interval_ms")
        if self.heartbeat_interval_ms <= 0:
            self.heartbeat_interval_ms = _cfg("wecom_bot.heartbeat_interval_ms")


@dataclass(slots=True)
class RuntimeLimitSettings:
    """运行时限制配置，包含最大并发请求数、系统任务并发数和繁忙提示文本。"""
    max_concurrent_requests: int = 0
    max_system_task_concurrency: int = 0
    _busy_reply_text: str = field(default="", init=False, repr=False)

    def _fill_defaults(self) -> None:
        if self.max_concurrent_requests <= 0:
            self.max_concurrent_requests = _cfg("runtime.max_concurrent_requests")
        if self.max_system_task_concurrency <= 0:
            self.max_system_task_concurrency = _cfg("runtime.max_system_task_concurrency")
        if not self._busy_reply_text:
            self._busy_reply_text = _cfg("runtime.busy_reply_text")

    @property
    def busy_reply_text(self) -> str:
        return self._busy_reply_text


@dataclass(slots=True)
class Settings:
    """顶层配置数据类，聚合企业微信机器人、日志、运行时和 Agent 所有子配置。"""
    wecom_bot: WeComBotSettings = field(default_factory=WeComBotSettings)
    logging: LoggingSettings = field(default_factory=LoggingSettings)
    runtime: RuntimeLimitSettings = field(default_factory=RuntimeLimitSettings)
    agent: AgentSettings = field(default_factory=AgentSettings)

    def fill_defaults(self) -> None:
        self.wecom_bot._fill_defaults()
        self.logging._fill_defaults()
        self.runtime._fill_defaults()
        self.agent._fill_defaults()


def default_agent_providers() -> dict[str, AgentProviderSettings]:
    return {
        "openai": AgentProviderSettings(
            label="OpenAI",
            type="openai",
            model="",
        ),
        "dashscope": AgentProviderSettings(
            label="DashScope",
            type="dashscope",
            model="",
        ),
        "custom": AgentProviderSettings(
            label="自定义 / 本地模型",
            type="openai_compatible",
            model="",
            base_url="",
        ),
    }


def validate_settings(settings: Settings, *, require_bot_credentials: bool = True) -> None:
    if require_bot_credentials and not settings.wecom_bot.bot_id:
        raise ConfigError("wecom_bot.bot_id 是必填项。")

    if require_bot_credentials and not settings.wecom_bot.secret:
        raise ConfigError("wecom_bot.secret 是必填项。")

    if settings.agent.provider and settings.agent.provider not in settings.agent.providers:
        raise ConfigError("agent.provider 必须指向一个已配置的提供商。")

    provider = settings.agent.providers.get(settings.agent.provider)
    if settings.agent.enabled:
        if not provider:
            raise ConfigError(f"提供商 '{settings.agent.provider}' 未配置。")
        if not provider.model.strip():
            raise ConfigError("智能体启用时，提供商的 model 不能为空。")

    if settings.agent.timeout_seconds <= 0:
        raise ConfigError("agent.timeout_seconds 必须大于 0。")

    if settings.agent.max_iterations <= 0:
        raise ConfigError("agent.max_iterations 必须大于 0。")

    if settings.agent.context.compression_trigger_chars <= 0:
        raise ConfigError("agent.context.compression_trigger_chars 必须大于 0。")
