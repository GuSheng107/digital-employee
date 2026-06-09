from __future__ import annotations

import json
import sqlite3
from pathlib import Path
from typing import Any
from uuid import uuid4

from app.db.core import _json_array, _json_object, connect_database, initialize_database
from app.utils import utc_now

_MCP_SUPPORTED_TRANSPORTS = {"stdio", "http", "sse", "streamable_http", "websocket"}
_MCP_TRANSPORT_ALIASES = {
    "stdio": "stdio",
    "http": "http",
    "sse": "sse",
    "streamable_http": "streamable_http",
    "streamable-http": "streamable_http",
    "streamablehttp": "streamable_http",
    "websocket": "websocket",
}


def _canonicalize_mcp_transport(value: Any, default: str = "stdio") -> str:
    normalized = str(value or "").strip().lower()
    if not normalized:
        normalized = default
    return _MCP_TRANSPORT_ALIASES.get(normalized, normalized)


def _normalize_mcp_server_type(server_type: Any, config: Any = None) -> str:
    raw = dict(config) if isinstance(config, dict) else {}
    transport = (
        server_type
        or raw.get("transport")
        or raw.get("type")
        or ("stdio" if raw.get("command") else "")
        or ("http" if raw.get("url") else "")
        or "stdio"
    )
    return _canonicalize_mcp_transport(transport)


def _normalize_mcp_server_config(server_type: str, config: Any) -> dict[str, Any]:
    raw = dict(config) if isinstance(config, dict) else {}
    normalized_type = _normalize_mcp_server_type(server_type, raw)

    if normalized_type == "stdio":
        result: dict[str, Any] = {
            "transport": "stdio",
            "command": str(raw.get("command", "")),
            "args": list(raw.get("args", [])) if isinstance(raw.get("args"), list) else [],
        }
        env = raw.get("env")
        if isinstance(env, dict) and env:
            result["env"] = {str(k): str(v) for k, v in env.items()}
        return result

    if normalized_type in _MCP_SUPPORTED_TRANSPORTS:
        return {
            "transport": normalized_type,
            "url": str(raw.get("url", "")),
            "headers": dict(raw.get("headers", {})) if isinstance(raw.get("headers"), dict) else {},
        }

    return raw


def _mcp_server_tools_from_row(row: Any) -> list[dict[str, Any]]:
    if row is None:
        return []
    tools = _json_array(row["tools_json"])
    return [item for item in tools if isinstance(item, dict)]


def _mcp_server_requires_backfill(
    row: Any,
    normalized_type: str,
    normalized_config: dict[str, Any],
    normalized_tools: list[dict[str, Any]],
) -> bool:
    stored_type = str(row["server_type"] or "stdio")
    stored_config = _json_object(row["config_json"])
    stored_tools = _mcp_server_tools_from_row(row)
    return (
        stored_type != normalized_type
        or stored_config != normalized_config
        or stored_tools != normalized_tools
    )


def _backfill_mcp_server_row(conn: sqlite3.Connection, row: Any) -> Any:
    normalized_type = _normalize_mcp_server_type(row["server_type"], _json_object(row["config_json"]))
    normalized_config = _normalize_mcp_server_config(normalized_type, _json_object(row["config_json"]))
    normalized_tools = _mcp_server_tools_from_row(row)
    if not _mcp_server_requires_backfill(row, normalized_type, normalized_config, normalized_tools):
        return row
    now = utc_now()
    conn.execute(
        """
        UPDATE mcp_server_config
        SET server_type = ?, config_json = ?, tools_json = ?, updated_at = ?
        WHERE server_id = ?
        """,
        (
            normalized_type,
            json.dumps(normalized_config, ensure_ascii=False, sort_keys=True),
            json.dumps(normalized_tools, ensure_ascii=False, sort_keys=True),
            now,
            str(row["server_id"]),
        ),
    )
    return conn.execute(
        """
        SELECT server_id, name, server_type, config_json, tools_json, is_active, scope, created_at, updated_at
        FROM mcp_server_config
        WHERE server_id = ?
        """,
        (str(row["server_id"]),),
    ).fetchone()


def _mcp_server_from_row(row: Any) -> dict[str, Any]:
    normalized_type = _normalize_mcp_server_type(row["server_type"], _json_object(row["config_json"]))
    scope = str(row["scope"]) if "scope" in row.keys() else "bot"
    return {
        "server_id": str(row["server_id"]),
        "name": str(row["name"]),
        "server_type": normalized_type,
        "config": _normalize_mcp_server_config(normalized_type, _json_object(row["config_json"])),
        "tools": _mcp_server_tools_from_row(row),
        "is_active": bool(row["is_active"]),
        "scope": scope or "bot",
        "created_at": str(row["created_at"]),
        "updated_at": str(row["updated_at"]),
    }


def _validate_mcp_server_name_unique(
    conn: sqlite3.Connection,
    name: str,
    *,
    exclude_server_id: str | None = None,
) -> None:
    row = conn.execute(
        """
        SELECT server_id
        FROM mcp_server_config
        WHERE name = ? AND (? IS NULL OR server_id <> ?)
        LIMIT 1
        """,
        (name, exclude_server_id, exclude_server_id),
    ).fetchone()
    if row is not None:
        raise ValueError("MCP 服务器名称必须唯一。")

    system_row = conn.execute(
        """
        SELECT server_id
        FROM mcp_server_config
        WHERE name = ? AND scope = 'system' AND (? IS NULL OR server_id <> ?)
        LIMIT 1
        """,
        (name, exclude_server_id, exclude_server_id),
    ).fetchone()
    if system_row is not None:
        raise ValueError("MCP 服务器名称与系统级服务器冲突，请更换名称。")


def save_mcp_tool_catalog(database_path: Path, tools: list[dict[str, Any]]) -> None:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        for item in tools:
            server_name = str(item.get("server_name") or "default")
            tool_name = str(item.get("name") or item.get("tool_name") or "").strip()
            if not tool_name:
                continue
            tool_id = f"{server_name}:{tool_name}"
            conn.execute(
                """
                INSERT INTO mcp_tool_catalog (
                    id, server_name, tool_name, description, enabled,
                    last_seen_at, metadata_json
                )
                VALUES (?, ?, ?, ?, 1, ?, ?)
                ON CONFLICT(id) DO UPDATE SET
                    description = excluded.description,
                    enabled = 1,
                    last_seen_at = excluded.last_seen_at,
                    metadata_json = excluded.metadata_json
                """,
                (
                    tool_id,
                    server_name,
                    tool_name,
                    str(item.get("description") or ""),
                    now,
                    json.dumps(item, ensure_ascii=False, sort_keys=True),
                ),
            )


def list_mcp_tool_catalog(database_path: Path) -> list[dict[str, Any]]:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        rows = conn.execute(
            """
            SELECT id, server_name, tool_name, description, enabled, last_seen_at, metadata_json
            FROM mcp_tool_catalog
            ORDER BY server_name, tool_name
            """
        ).fetchall()
    return [dict(row) for row in rows]


def list_mcp_servers(database_path: Path) -> list[dict[str, Any]]:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        rows = conn.execute(
            "SELECT server_id, name, server_type, config_json, tools_json, is_active, scope, created_at, updated_at FROM mcp_server_config ORDER BY created_at DESC"
        ).fetchall()
    return [_mcp_server_from_row(row) for row in rows]


def get_mcp_server(database_path: Path, server_id: str) -> dict[str, Any] | None:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        row = conn.execute(
            "SELECT server_id, name, server_type, config_json, tools_json, is_active, scope, created_at, updated_at FROM mcp_server_config WHERE server_id = ?",
            (server_id,),
        ).fetchone()
        if row is None:
            return None
    return _mcp_server_from_row(row)


def upsert_mcp_server(database_path: Path, payload: dict[str, Any]) -> dict[str, Any]:
    initialize_database(database_path)
    now = utc_now()
    server_id = payload.get("server_id", str(uuid4()))
    name = payload.get("name", "").strip()
    server_type = payload.get("server_type", "stdio")
    config = payload.get("config", {})
    tools = payload.get("tools", [])
    is_active = payload.get("is_active", False)

    if not name:
        raise ValueError("服务器名称不能为空。")

    normalized_server_type = _normalize_mcp_server_type(server_type, config)
    if normalized_server_type not in _MCP_SUPPORTED_TRANSPORTS:
        raise ValueError(f"不支持的 MCP 传输协议：{server_type}")
    formatted_config = _normalize_mcp_server_config(normalized_server_type, config)

    with connect_database(database_path) as conn:
        _validate_mcp_server_name_unique(conn, name, exclude_server_id=str(server_id))
        existing = conn.execute(
            "SELECT name, server_type, config_json, tools_json, is_active, scope FROM mcp_server_config WHERE server_id = ?",
            (server_id,),
        ).fetchone()
        existing_scope = str(existing["scope"]) if existing and "scope" in existing.keys() else "bot"
        if existing and existing_scope == "system":
            raise ValueError("系统级 MCP 服务器不允许编辑")
        existing_server_type = _normalize_mcp_server_type(
            existing["server_type"] if existing else normalized_server_type,
            _json_object(existing["config_json"]) if existing else {},
        )
        existing_config = _normalize_mcp_server_config(
            existing_server_type,
            _json_object(existing["config_json"]) if existing else {},
        )
        is_edit_mode = bool(existing)
        should_reset_runtime_state = is_edit_mode and "tools" not in payload
        if should_reset_runtime_state:
            tools_to_save: list[dict[str, Any]] = []
            is_active_to_save = False
        else:
            tools_to_save = [item for item in tools if isinstance(item, dict)] if "tools" in payload else _mcp_server_tools_from_row(existing)
            if "is_active" in payload:
                is_active_to_save = bool(is_active)
            else:
                is_active_to_save = bool(existing["is_active"]) if existing else False
        if existing:
            scope = existing_scope
        else:
            raw_scope = str(payload.get("scope") or "").strip().lower()
            scope = "system" if raw_scope == "system" else "bot"
        try:
            conn.execute(
                """
                INSERT INTO mcp_server_config (server_id, name, server_type, config_json, tools_json, is_active, scope, created_at, updated_at)
                VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(server_id) DO UPDATE SET
                    name = excluded.name,
                    server_type = excluded.server_type,
                    config_json = excluded.config_json,
                    tools_json = excluded.tools_json,
                    is_active = excluded.is_active,
                    updated_at = excluded.updated_at
                """,
                (
                    server_id,
                    name,
                    normalized_server_type,
                    json.dumps(formatted_config, ensure_ascii=False, sort_keys=True),
                    json.dumps(tools_to_save, ensure_ascii=False, sort_keys=True),
                    int(is_active_to_save),
                    scope,
                    now,
                    now,
                ),
            )
        except sqlite3.IntegrityError as exc:
            if "mcp_server_config.name" in str(exc) or "idx_mcp_server_config_unique_name" in str(exc):
                raise ValueError("MCP 服务器名称必须唯一。") from exc
            raise
    return get_mcp_server(database_path, server_id)


def delete_mcp_server(database_path: Path, server_id: str) -> bool:
    initialize_database(database_path)
    with connect_database(database_path) as conn:
        row = conn.execute(
            "SELECT scope, name FROM mcp_server_config WHERE server_id = ?",
            (server_id,),
        ).fetchone()
        if row is None:
            return False
        if str(row["scope"]) == "system":
            raise ValueError("系统级 MCP 服务器不允许删除")
        server_name = str(row["name"])
        conn.execute("DELETE FROM bot_mcp_mapping WHERE server_id = ?", (server_id,))
        conn.execute("DELETE FROM mcp_tool_catalog WHERE server_name = ?", (server_name,))
        cursor = conn.execute("DELETE FROM mcp_server_config WHERE server_id = ?", (server_id,))
    return cursor.rowcount > 0


def toggle_mcp_server(database_path: Path, server_id: str, is_active: bool) -> None:
    initialize_database(database_path)
    now = utc_now()
    with connect_database(database_path) as conn:
        row = conn.execute(
            "SELECT scope, tools_json FROM mcp_server_config WHERE server_id = ?",
            (server_id,),
        ).fetchone()
        if row is None:
            raise ValueError("未找到对应的 MCP 服务器。")
        if str(row["scope"]) == "system":
            raise ValueError("系统级 MCP 服务器不允许修改启用状态")
        if is_active and not _json_array(row["tools_json"]):
            raise ValueError("请先刷新工具列表，确认服务可用后再启用。")
        conn.execute(
            "UPDATE mcp_server_config SET is_active = ?, updated_at = ? WHERE server_id = ?",
            (int(is_active), now, server_id),
        )


async def discover_mcp_tools(settings: Any) -> list[dict[str, Any]]:
    from app.config_loader import Settings
    if not settings.agent.mcp.enabled or not settings.agent.mcp.servers:
        return []

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError as exc:
        raise RuntimeError("langchain-mcp-adapters is not installed.") from exc

    client = MultiServerMCPClient(settings.agent.mcp.servers)
    tools = await client.get_tools()
    result: list[dict[str, Any]] = []
    for tool in tools:
        result.append(
            {
                "server_name": _infer_server_name(tool, settings),
                "name": str(getattr(tool, "name", "")),
                "description": str(getattr(tool, "description", "")),
                "args_schema": _schema_to_jsonable(getattr(tool, "args_schema", None)),
            }
        )
    return result


def _infer_server_name(tool: Any, settings: Any) -> str:
    name = str(getattr(tool, "name", ""))
    server_names = list(settings.agent.mcp.servers.keys()) if hasattr(settings.agent.mcp.servers, 'keys') else list(settings.agent.mcp.servers)
    for server_name in server_names:
        if name.startswith(f"{server_name}_") or name.startswith(f"{server_name}."):
            return server_name
    if len(server_names) == 1:
        return next(iter(server_names))
    best_match = ""
    best_len = 0
    for server_name in server_names:
        if server_name in name and len(server_name) > best_len:
            best_match = server_name
            best_len = len(server_name)
    if best_match:
        return best_match
    return "mcp"


def _schema_to_jsonable(schema: Any) -> dict[str, Any]:
    if schema is None:
        return {}
    try:
        if hasattr(schema, "model_json_schema"):
            return schema.model_json_schema()
        if hasattr(schema, "schema"):
            return schema.schema()
    except Exception:
        return {}
    try:
        json.dumps(schema)
        return schema if isinstance(schema, dict) else {}
    except TypeError:
        return {}

