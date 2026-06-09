from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from app.config_loader import (
    AgentProviderSettings,
    AgentSettings,
    ContextSettings,
    LoggingSettings,
    MCPSettings,
    RuntimeLimitSettings,
    Settings,
    SkillSettings,
    WeComBotSettings,
    default_agent_providers,
)
from app.crypto_utils import get_crypto_utils
from app.db.core import (
    connect_database,
    initialize_database,
)
from app.db.bot_store import _bot_dict_from_row
from app.exceptions import CryptoError
from app.yaml_config import get_yaml_config


def load_settings_from_database(
    database_path: Path,
    *,
    bot_key: str | None = None,
) -> Settings:
    target_path = initialize_database(database_path)
    crypto = get_crypto_utils()
    yaml_cfg = get_yaml_config()

    with connect_database(target_path) as conn:
        named_bot_row = None
        if bot_key:
            named_bot_row = conn.execute(
                "SELECT * FROM bot_config WHERE bot_key = ?",
                (bot_key,),
            ).fetchone()

        providers = _load_providers(conn, crypto)
        enabled_skills = _load_enabled_skills(conn, bot_key=bot_key)
        mcp_settings = _load_mcp_settings(conn, bot_key=bot_key)

    provider_key = _resolve_provider_key(
        yaml_cfg.get("agent.provider"),
        providers,
    )

    logging_settings = LoggingSettings()
    runtime_settings = RuntimeLimitSettings()
    agent_settings = AgentSettings(
        provider=provider_key,
        providers=providers,
        mcp=mcp_settings,
        skills=SkillSettings(enabled=enabled_skills),
        context=ContextSettings(),
    )

    wecom_bot_settings = WeComBotSettings()

    if named_bot_row is not None:
        named_bot = _bot_dict_from_row(named_bot_row)
        wecom_bot_settings = WeComBotSettings(
            name=str(named_bot["name"]),
            bot_id=str(named_bot["bot_id"]),
            secret=str(named_bot["secret"]),
        )
        if str(named_bot.get("system_prompt", "")).strip():
            agent_settings.system_prompt = str(named_bot["system_prompt"]).strip()
        bot_agent_provider = str(named_bot["agent_provider"] or "").strip()
        if bot_agent_provider:
            agent_settings.provider = bot_agent_provider
        else:
            agent_settings.enabled = False
        if not str(named_bot["bound_chat_id"] or "").strip():
            agent_settings.enabled = False

    settings = Settings(
        wecom_bot=wecom_bot_settings,
        logging=logging_settings,
        runtime=runtime_settings,
        agent=agent_settings,
    )
    settings.fill_defaults()
    return settings


def get_platform_settings() -> dict[str, Any]:
    yaml_cfg = get_yaml_config()
    logging_level = yaml_cfg.get("logging.level")
    # 只允许 INFO、WARNING、ERROR，其他转为 INFO
    if logging_level not in ("INFO", "WARNING", "ERROR"):
        logging_level = "INFO"
    return {
        "context_length_limit": yaml_cfg.get("agent.context_length_limit"),
        "platform_agent_provider": yaml_cfg.get("agent.provider"),
        "platform_agent_timeout_seconds": yaml_cfg.get("agent.timeout_seconds"),
        "platform_agent_max_iterations": yaml_cfg.get("agent.max_iterations"),
        "document_max_characters": yaml_cfg.get("doc.max_characters"),
        "memory_update_max_pairs": yaml_cfg.get("memory_update.max_pairs"),
        "memory_update_max_chars": yaml_cfg.get("memory_update.max_chars"),
        "thread_pool_max_workers": yaml_cfg.get("runtime.max_concurrent_requests"),
        "attachment_reply": yaml_cfg.get("runtime.attachment_reply"),
        "guest_account_enabled": yaml_cfg.get("guest_account.enabled"),
        "feedback_alert_enabled": yaml_cfg.get("feedback_alert.enabled"),
        "feedback_alert_threshold": yaml_cfg.get("feedback_alert.threshold"),
        "feedback_alert_window_minutes": yaml_cfg.get("feedback_alert.window_minutes"),
        "feedback_alert_cooldown_minutes": yaml_cfg.get("feedback_alert.cooldown_minutes"),
        "agent_max_reasoning_chars": yaml_cfg.get("agent.max_reasoning_chars"),
        "agent_max_output_chars": yaml_cfg.get("agent.max_output_chars"),
        "agent_max_stream_chunks": yaml_cfg.get("agent.max_stream_chunks"),
        "agent_truncation_notice": yaml_cfg.get("agent.truncation_notice"),
        "agent_reply_notice": yaml_cfg.get("agent.reply_notice"),
        "agent_fallback_text": yaml_cfg.get("agent.fallback_text"),
        "mcp_max_tool_event_payload_chars": yaml_cfg.get("mcp.max_tool_event_payload_chars"),
        "mcp_max_result_chars": yaml_cfg.get("mcp.max_result_chars"),
        "skills_max_script_output_chars": yaml_cfg.get("skills.max_script_output_chars"),
        "logging_level": logging_level,
        "agent_compression_transcript_max_chars": yaml_cfg.get("agent.compression_transcript_max_chars"),
        "agent_max_cache_size": yaml_cfg.get("agent.max_cache_size"),
        "agent_recent_context_max_chars": yaml_cfg.get("agent.recent_context_max_chars"),
        "agent_recent_context_max_messages": yaml_cfg.get("agent.recent_context_max_messages"),
        "agent_recent_context_fetch_multiplier": yaml_cfg.get("agent.recent_context_fetch_multiplier"),
        "agent_context_message_max_chars": yaml_cfg.get("agent.context_message_max_chars"),
        "agent_summary_in_prompt_max_chars": yaml_cfg.get("agent.summary_in_prompt_max_chars"),
        "agent_system_prompt_max_chars": yaml_cfg.get("agent.system_prompt_max_chars"),
        "agent_max_image_bytes": yaml_cfg.get("agent.max_image_bytes"),
        "agent_max_video_bytes": yaml_cfg.get("agent.max_video_bytes"),
        "agent_max_audio_bytes": yaml_cfg.get("agent.max_audio_bytes"),
        "agent_max_file_bytes": yaml_cfg.get("agent.max_file_bytes"),
        "runtime_max_system_task_concurrency": yaml_cfg.get("runtime.max_system_task_concurrency"),
        "skills_max_tool_description_chars": yaml_cfg.get("skills.max_tool_description_chars"),
        "memory_query_expansion_enabled": yaml_cfg.get("memory.query_expansion.enabled"),
    }


_FIELD_TO_YAML = {
    "context_length_limit": "agent.context_length_limit",
    "platform_agent_provider": "agent.provider",
    "platform_agent_timeout_seconds": "agent.timeout_seconds",
    "platform_agent_max_iterations": "agent.max_iterations",
    "document_max_characters": "doc.max_characters",
    "memory_update_max_pairs": "memory_update.max_pairs",
    "memory_update_max_chars": "memory_update.max_chars",
    "thread_pool_max_workers": "runtime.max_concurrent_requests",
    "attachment_reply": "runtime.attachment_reply",
    "guest_account_enabled": "guest_account.enabled",
    "feedback_alert_enabled": "feedback_alert.enabled",
    "feedback_alert_threshold": "feedback_alert.threshold",
    "feedback_alert_window_minutes": "feedback_alert.window_minutes",
    "feedback_alert_cooldown_minutes": "feedback_alert.cooldown_minutes",
    "agent_max_reasoning_chars": "agent.max_reasoning_chars",
    "agent_max_output_chars": "agent.max_output_chars",
    "agent_max_stream_chunks": "agent.max_stream_chunks",
    "agent_truncation_notice": "agent.truncation_notice",
    "agent_reply_notice": "agent.reply_notice",
    "agent_fallback_text": "agent.fallback_text",
    "mcp_max_tool_event_payload_chars": "mcp.max_tool_event_payload_chars",
    "mcp_max_result_chars": "mcp.max_result_chars",
    "skills_max_script_output_chars": "skills.max_script_output_chars",
    "logging_level": "logging.level",
    "agent_compression_transcript_max_chars": "agent.compression_transcript_max_chars",
    "agent_max_cache_size": "agent.max_cache_size",
    "agent_recent_context_max_chars": "agent.recent_context_max_chars",
    "agent_recent_context_max_messages": "agent.recent_context_max_messages",
    "agent_recent_context_fetch_multiplier": "agent.recent_context_fetch_multiplier",
    "agent_context_message_max_chars": "agent.context_message_max_chars",
    "agent_summary_in_prompt_max_chars": "agent.summary_in_prompt_max_chars",
    "agent_system_prompt_max_chars": "agent.system_prompt_max_chars",
    "agent_max_image_bytes": "agent.max_image_bytes",
    "agent_max_video_bytes": "agent.max_video_bytes",
    "agent_max_audio_bytes": "agent.max_audio_bytes",
    "agent_max_file_bytes": "agent.max_file_bytes",
    "runtime_max_system_task_concurrency": "runtime.max_system_task_concurrency",
    "skills_max_tool_description_chars": "skills.max_tool_description_chars",
    "memory_query_expansion_enabled": "memory.query_expansion.enabled",
}


def upsert_platform_settings(updates: dict[str, Any]) -> dict[str, Any]:
    yaml_cfg = get_yaml_config()
    for api_field, yaml_path in _FIELD_TO_YAML.items():
        if api_field in updates:
            value = updates[api_field]
            if api_field == "logging_level" and value not in ("INFO", "WARNING", "ERROR"):
                value = "INFO"
            yaml_cfg.set(yaml_path, value)
    yaml_cfg.save()
    yaml_cfg.reload()
    return get_platform_settings()


def _load_providers(conn: Any, crypto: Any) -> dict[str, AgentProviderSettings]:
    rows = conn.execute(
        "SELECT * FROM agent_provider_config ORDER BY provider_key"
    ).fetchall()
    providers = default_agent_providers()
    for row in rows:
        try:
            api_key = crypto.decrypt(str(row["api_key"]))
        except CryptoError:
            api_key = ""
        model_kwargs: dict[str, Any] = {}
        try:
            model_kwargs = json.loads(str(row["model_kwargs_json"] or "{}"))
        except (json.JSONDecodeError, TypeError):
            pass
        capabilities: list[str] = []
        try:
            capabilities = json.loads(str(row["capabilities_json"] or "[]"))
        except (json.JSONDecodeError, TypeError):
            pass
        built_in_tools: list[dict[str, Any]] = []
        try:
            built_in_tools = json.loads(str(row["built_in_tools_json"] or "[]"))
        except (json.JSONDecodeError, TypeError):
            pass
        providers[str(row["provider_key"])] = AgentProviderSettings(
            label=str(row["label"]),
            type=str(row["provider_type"]),
            model=str(row["model"]),
            base_url=str(row["base_url"]),
            api_key=api_key,
            temperature=float(row["temperature"]),
            timeout_seconds=int(row["timeout_seconds"]),
            max_retries=int(row["max_retries"]),
            model_kwargs=model_kwargs,
            capabilities=capabilities,
            built_in_tools=built_in_tools,
        )
    return providers


def _load_enabled_skills(conn: Any, *, bot_key: str | None = None) -> list[str]:
    skill_names: list[str] = []

    system_rows = conn.execute(
        "SELECT skill_name FROM skill_config WHERE scope = 'system' AND enabled = 1 ORDER BY skill_name"
    ).fetchall()
    skill_names.extend(str(r["skill_name"]) for r in system_rows)

    if bot_key:
        bot_rows = conn.execute(
            """
            SELECT bm.skill_name
            FROM bot_skill_mapping AS bm
            JOIN skill_config AS sc ON sc.skill_name = bm.skill_name
            WHERE bm.bot_key = ?
              AND sc.enabled = 1
              AND COALESCE(sc.scope, 'bot') = 'bot'
            ORDER BY bm.skill_name
            """,
            (bot_key,),
        ).fetchall()
        for r in bot_rows:
            name = str(r["skill_name"])
            if name not in skill_names:
                skill_names.append(name)
    else:
        bot_rows = conn.execute(
            "SELECT skill_name FROM skill_config WHERE scope = 'bot' AND enabled = 1 ORDER BY skill_name"
        ).fetchall()
        for r in bot_rows:
            name = str(r["skill_name"])
            if name not in skill_names:
                skill_names.append(name)

    return skill_names


def _load_mcp_settings(
    conn: Any,
    *,
    bot_key: str | None = None,
) -> MCPSettings:
    server_ids: list[str] = []

    system_rows = conn.execute(
        "SELECT server_id FROM mcp_server_config WHERE scope = 'system' AND is_active = 1 ORDER BY server_id"
    ).fetchall()
    for r in system_rows:
        sid = str(r["server_id"])
        if sid not in server_ids:
            server_ids.append(sid)

    if bot_key:
        bot_rows = conn.execute(
            """
            SELECT bm.server_id
            FROM bot_mcp_mapping AS bm
            JOIN mcp_server_config AS ms ON ms.server_id = bm.server_id
            WHERE bm.bot_key = ?
              AND ms.is_active = 1
              AND COALESCE(ms.scope, 'bot') = 'bot'
            ORDER BY bm.server_id
            """,
            (bot_key,),
        ).fetchall()
        for r in bot_rows:
            sid = str(r["server_id"])
            if sid not in server_ids:
                server_ids.append(sid)
    else:
        bot_rows = conn.execute(
            "SELECT server_id FROM mcp_server_config WHERE scope = 'bot' AND is_active = 1 ORDER BY server_id"
        ).fetchall()
        for r in bot_rows:
            sid = str(r["server_id"])
            if sid not in server_ids:
                server_ids.append(sid)

    if not server_ids:
        return MCPSettings(enabled=False, servers={})

    placeholders = ",".join("?" for _ in server_ids)
    rows = conn.execute(
        f"""
        SELECT server_id, name, server_type, config_json
        FROM mcp_server_config
        WHERE server_id IN ({placeholders})
          AND is_active = 1
        ORDER BY name
        """,
        server_ids,
    ).fetchall()

    if not rows:
        return MCPSettings(enabled=False, servers={})

    servers: dict[str, Any] = {}
    for row in rows:
        config = json.loads(str(row["config_json"]))
        servers[str(row["name"])] = config

    return MCPSettings(enabled=True, servers=servers)


def _resolve_provider_key(raw: str, providers: dict[str, AgentProviderSettings]) -> str:
    if raw and raw in providers:
        return raw
    if providers:
        return next(iter(providers))
    return "openai"
