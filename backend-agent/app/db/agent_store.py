from __future__ import annotations

import sqlite3
from pathlib import Path
from typing import Any

from app.config_loader import AgentProviderSettings
from app.crypto_utils import get_crypto_utils
from app.db.core import _row_value, connect_database, initialize_database
from app.exceptions import CryptoError
from app.utils import utc_now

SUPPORTED_PROVIDER_TYPES = {"openai", "dashscope", "openai_compatible", "zhipu", "minimax", "moonshot", "deepseek", "claude", "gemini"}


def _normalize_json_text(raw: Any, *, empty_fallback: str) -> str:
    text = str(raw or "").strip()
    if not text:
        return empty_fallback
    try:
        import json

        parsed = json.loads(text)
    except Exception:
        return text

    if parsed is None:
        return empty_fallback
    if isinstance(parsed, dict) and not parsed:
        return empty_fallback
    if isinstance(parsed, list) and not parsed:
        return empty_fallback
    return json.dumps(parsed, ensure_ascii=False, sort_keys=False)


def list_agents(database_path: Path, page: int = 1, page_size: int = 10, keyword: str = "") -> dict[str, Any]:
    initialize_database(database_path)
    current_page = max(1, int(page or 1))
    current_page_size = min(max(1, int(page_size or 10)), 100)
    search_keyword = str(keyword or "").strip()
    clauses: list[str] = []
    params: list[Any] = []
    if search_keyword:
        clauses.append(
            "(provider_key LIKE ? OR label LIKE ? OR provider_type LIKE ? OR model LIKE ? OR provider_name LIKE ?)"
        )
        pattern = f"%{search_keyword}%"
        params.extend([pattern, pattern, pattern, pattern, pattern])
    where_sql = f"WHERE {' AND '.join(clauses)}" if clauses else ""

    with connect_database(database_path) as conn:
        count_row = conn.execute(
            f"SELECT COUNT(*) as total FROM agent_provider_config {where_sql}",
            params,
        ).fetchone()
        total = count_row["total"]

        offset = (current_page - 1) * current_page_size
        rows = conn.execute(
            f"""
            SELECT *
            FROM agent_provider_config
            {where_sql}
            ORDER BY provider_key
            LIMIT ? OFFSET ?
            """,
            [*params, current_page_size, offset],
        ).fetchall()

    agents = [
        {
            "provider_key": str(row["provider_key"]),
            "label": str(row["label"]),
            "provider_type": str(row["provider_type"]),
            "model": str(row["model"]),
            "base_url": str(row["base_url"]),
            "temperature": float(row["temperature"]),
            "timeout_seconds": int(row["timeout_seconds"]),
            "max_retries": int(row["max_retries"]),
            "model_kwargs_json": _normalize_json_text(_row_value(row, "model_kwargs_json", ""), empty_fallback=""),
            "capabilities_json": _normalize_json_text(_row_value(row, "capabilities_json", ""), empty_fallback=""),
            "built_in_tools_json": _normalize_json_text(_row_value(row, "built_in_tools_json", ""), empty_fallback=""),
            "is_active": bool(row["is_active"]),
            "last_test_status": str(row["last_test_status"]),
            "last_test_time": str(row["last_test_time"]),
            "last_test_trace_id": str(row["last_test_trace_id"]),
            "provider_name": str(_row_value(row, "provider_name", "")),
            "created_at": str(row["created_at"]),
            "updated_at": str(row["updated_at"]),
        }
        for row in rows
    ]

    total_pages = (total + current_page_size - 1) // current_page_size if total > 0 else 1
    return {
        "agents": agents,
        "total": total,
        "page": current_page,
        "page_size": current_page_size,
        "total_pages": total_pages
    }


def get_agent(
    database_path: Path,
    provider_key: str,
    *,
    decrypt_api_key: bool = False,
) -> dict[str, Any] | None:
    initialize_database(database_path)
    crypto = get_crypto_utils() if decrypt_api_key else None
    with connect_database(database_path) as conn:
        row = conn.execute("SELECT * FROM agent_provider_config WHERE provider_key = ?", (provider_key,)).fetchone()
    if not row:
        return None
    if crypto:
        try:
            api_key = crypto.decrypt(str(row["api_key"]))
        except CryptoError:
            api_key = ""
    else:
        api_key = str(row["api_key"])
    return {
        "provider_key": str(row["provider_key"]),
        "label": str(row["label"]),
        "provider_type": str(row["provider_type"]),
        "model": str(row["model"]),
        "base_url": str(row["base_url"]),
        "api_key": api_key,
        "temperature": float(row["temperature"]),
        "timeout_seconds": int(row["timeout_seconds"]),
        "max_retries": int(row["max_retries"]),
        "model_kwargs_json": _normalize_json_text(_row_value(row, "model_kwargs_json", ""), empty_fallback=""),
        "capabilities_json": _normalize_json_text(_row_value(row, "capabilities_json", ""), empty_fallback=""),
        "built_in_tools_json": _normalize_json_text(_row_value(row, "built_in_tools_json", ""), empty_fallback=""),
        "is_active": bool(row["is_active"]),
        "last_test_status": str(row["last_test_status"]),
        "last_test_time": str(row["last_test_time"]),
        "last_test_trace_id": str(row["last_test_trace_id"]),
        "provider_name": str(_row_value(row, "provider_name", "")),
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def upsert_agent(database_path: Path, provider_key: str, agent_data: dict[str, Any]) -> dict[str, Any]:
    initialize_database(database_path)
    now = utc_now()
    crypto = get_crypto_utils()

    raw_provider_type = str(agent_data.get("provider_type", "")).strip()
    if raw_provider_type not in SUPPORTED_PROVIDER_TYPES:
        raise ValueError("不支持的 provider_type，请使用 openai、dashscope 或 openai_compatible。")
    provider_type = raw_provider_type
    provider_name = str(agent_data.get("provider_name", "")).strip()
    if provider_type != "openai_compatible" and not provider_name:
        type_names = {
            "openai": "OpenAI",
            "dashscope": "DashScope",
            "zhipu": "ZhipuAI",
            "minimax": "MiniMax",
            "moonshot": "Moonshot",
            "deepseek": "DeepSeek",
            "claude": "Anthropic",
            "gemini": "Google",
        }
        provider_name = type_names.get(provider_type, provider_type)

    with connect_database(database_path) as conn:
        existing = conn.execute("SELECT * FROM agent_provider_config WHERE provider_key = ?", (provider_key,)).fetchone()
        label = str(agent_data.get("label", "")).strip()
        duplicated = conn.execute(
            """
            SELECT provider_key
            FROM agent_provider_config
            WHERE lower(label) = lower(?) AND provider_key <> ?
            LIMIT 1
            """,
            (label, provider_key),
        ).fetchone()
        if label and duplicated:
            raise ValueError("Agent 标签必须唯一。")

        last_test_status = str(agent_data.get("last_test_status", existing["last_test_status"] if existing else "")).strip()
        last_test_time = str(agent_data.get("last_test_time", existing["last_test_time"] if existing else "")).strip()
        last_test_trace_id = str(agent_data.get("last_test_trace_id", existing["last_test_trace_id"] if existing else "")).strip()

        if existing and "api_key" not in agent_data:
            api_key_encrypted = str(existing["api_key"] or "")
        else:
            api_key_value = str(agent_data.get("api_key", ""))
            api_key_encrypted = crypto.encrypt(api_key_value)
            if existing:
                stored_api_key = str(existing["api_key"] or "")
                if api_key_value == stored_api_key:
                    try:
                        crypto.decrypt(stored_api_key)
                        api_key_encrypted = stored_api_key
                    except CryptoError:
                        api_key_encrypted = crypto.encrypt(api_key_value)

        raw_temperature = agent_data.get("temperature")
        raw_timeout_seconds = agent_data.get("timeout_seconds")
        raw_max_retries = agent_data.get("max_retries")
        temperature_to_save = (
            float(raw_temperature)
            if raw_temperature not in (None, "")
            else float(existing["temperature"] if existing else AgentProviderSettings.temperature)
        )
        timeout_seconds_to_save = (
            int(raw_timeout_seconds)
            if raw_timeout_seconds not in (None, "")
            else int(existing["timeout_seconds"] if existing else AgentProviderSettings.timeout_seconds)
        )
        max_retries_to_save = (
            int(raw_max_retries)
            if raw_max_retries not in (None, "")
            else int(existing["max_retries"] if existing else AgentProviderSettings.max_retries)
        )

        model_kwargs_json = _normalize_json_text(agent_data.get("model_kwargs_json", ""), empty_fallback="")
        capabilities_json = _normalize_json_text(agent_data.get("capabilities_json", ""), empty_fallback="")
        built_in_tools_json = _normalize_json_text(agent_data.get("built_in_tools_json", ""), empty_fallback="")

        try:
            conn.execute(
                """
                INSERT INTO agent_provider_config (
                    provider_key, label, provider_type, model, base_url, api_key,
                    temperature, timeout_seconds, max_retries,
                    model_kwargs_json, capabilities_json, built_in_tools_json,
                    is_active, provider_name, last_test_status, last_test_time, last_test_trace_id,
                    created_at, updated_at
                )
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(provider_key) DO UPDATE SET
                    label = excluded.label,
                    provider_type = excluded.provider_type,
                    model = excluded.model,
                    base_url = excluded.base_url,
                    api_key = excluded.api_key,
                    temperature = excluded.temperature,
                    timeout_seconds = excluded.timeout_seconds,
                    max_retries = excluded.max_retries,
                    model_kwargs_json = excluded.model_kwargs_json,
                    capabilities_json = excluded.capabilities_json,
                    built_in_tools_json = excluded.built_in_tools_json,
                    is_active = excluded.is_active,
                    provider_name = excluded.provider_name,
                    last_test_status = excluded.last_test_status,
                    last_test_time = excluded.last_test_time,
                    last_test_trace_id = excluded.last_test_trace_id,
                    updated_at = excluded.updated_at
                """,
                (
                    provider_key,
                    label,
                    provider_type,
                    agent_data.get("model", ""),
                    agent_data.get("base_url", ""),
                    api_key_encrypted,
                    temperature_to_save,
                    timeout_seconds_to_save,
                    max_retries_to_save,
                    model_kwargs_json,
                    capabilities_json,
                    built_in_tools_json,
                    int(bool(agent_data.get("is_active", False))),
                    provider_name,
                    last_test_status,
                    last_test_time,
                    last_test_trace_id,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            if "agent_provider_config.label" in str(exc) or "idx_agent_provider_config_unique_label" in str(exc):
                raise ValueError("Agent 标签必须唯一。") from exc
            raise
    updated_agent = get_agent(database_path, provider_key)
    if updated_agent is None:
        raise RuntimeError("Failed to save agent")
    return updated_agent


def delete_agent(database_path: Path, provider_key: str) -> bool:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        cursor = conn.execute("DELETE FROM agent_provider_config WHERE provider_key = ?", (provider_key,))
    return cursor.rowcount > 0


def update_agent_test_status(database_path: Path, provider_key: str, status: str, trace_id: str | None) -> None:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        conn.execute(
            """
            UPDATE agent_provider_config
            SET last_test_status = ?, last_test_time = ?, last_test_trace_id = ?, updated_at = ?
            WHERE provider_key = ?
            """,
            (status, now, trace_id or "", now, provider_key),
        )


def set_agent_active(database_path: Path, provider_key: str, is_active: bool) -> None:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        conn.execute(
            "UPDATE agent_provider_config SET is_active = ?, updated_at = ? WHERE provider_key = ?",
            (int(is_active), now, provider_key),
        )

