from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Body, Depends, Path as FastAPIPath, Request
from pathlib import Path

from app.api_response import ApiError
from app.db.mcp_store import (
    get_mcp_server,
    list_mcp_servers,
    list_mcp_tool_catalog,
    save_mcp_tool_catalog,
    toggle_mcp_server,
    upsert_mcp_server,
    delete_mcp_server,
    discover_mcp_tools,
    _schema_to_jsonable,
)
from app.config_loader import MCPSettings, AgentSettings, Settings
from app.db.settings_store import load_settings_from_database
from app.exceptions import NotFoundError, ValidationError
from app.routers._deps import get_database_path
from app.routers._utils import _collect_mcp_bot_usage, _enrich_bot_bound_item
from app.routers.auth import require_admin, require_non_guest

_DANGEROUS_COMMAND_PATTERNS = (
    "rm ",
    "rmdir",
    "del ",
    "format ",
    "mkfs.",
    "dd ",
    "> /dev/",
    "curl |",
    "wget |",
    "| bash",
    "| sh",
    "| python",
    "| perl",
    "/dev/null",
    "shutdown",
    "reboot",
)


def _validate_stdio_command(command: str, args: list[str]) -> None:
    combined = " ".join([command, *args]).lower()
    for pattern in _DANGEROUS_COMMAND_PATTERNS:
        if pattern in combined:
            raise ValidationError(
                f"启动命令包含潜在危险操作「{pattern.strip()}」，已拒绝。如确需使用，请手动编辑配置文件。"
            )

router = APIRouter(prefix="/api/mcp", tags=["mcp"])


def _assert_mcp_edit_allowed(
    existing_server: dict[str, Any],
    payload: dict[str, Any],
    usage: dict[str, Any] | None,
) -> None:
    if not usage or usage["mounted_bot_count"] <= 0:
        return
    raise ValidationError(
        f"MCP [{usage['item_label']}] 已被 Bot [{', '.join(usage['mounted_bot_names'])}] 挂载，无法编辑"
    )


@router.post("/tools/refresh", summary="刷新MCP工具列表", description="重新发现并刷新所有MCP服务器的工具列表")
async def refresh_mcp_tools(
    request: Request,
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    try:
        settings = load_settings_from_database(database_path)
        tools = await discover_mcp_tools(settings)
        save_mcp_tool_catalog(database_path, tools)
        return {"ok": True, "tools": list_mcp_tool_catalog(database_path)}
    except Exception as exc:
        raise ApiError(
            "MCP 工具刷新失败",
            status_code=400,
            log_message="Failed to refresh MCP tools.",
        ) from exc


@router.get("/tools", summary="获取MCP工具列表", description="获取所有已发现的MCP工具列表")
def get_mcp_tools(
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    return {"tools": list_mcp_tool_catalog(database_path)}


@router.get("/servers", summary="获取MCP服务器列表", description="获取所有MCP服务器配置列表")
def list_mcp_servers_api(
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    servers = list_mcp_servers(database_path)
    usage_map = _collect_mcp_bot_usage(
        database_path,
        [str(item.get("server_id") or "").strip() for item in servers],
    )
    return {
        "servers": [
            _enrich_bot_bound_item(item, usage_map.get(str(item.get("server_id") or "").strip()))
            for item in servers
        ]
    }


@router.get("/servers/{server_id}", summary="获取MCP服务器详情", description="获取指定MCP服务器的详细配置")
def get_mcp_server_api(
    server_id: str = FastAPIPath(..., description="MCP服务器ID"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    server = get_mcp_server(database_path, server_id)
    if server is None:
        raise NotFoundError("MCP server 未找到")
    usage_map = _collect_mcp_bot_usage(database_path, [server_id])
    return {"server": _enrich_bot_bound_item(server, usage_map.get(server_id))}


@router.post("/servers", summary="保存MCP服务器配置", description="创建或更新MCP服务器配置，包含危险命令的stdio配置会被拒绝")
def upsert_mcp_server_api(
    request: Request,
    payload: dict[str, Any] = Body(..., description="MCP服务器配置信息：server_id（字符串，可选，用于更新）、name（字符串，必填）、server_type（字符串，'stdio'或'http'）、config（对象，根据server_type不同）、is_active（布尔）、scope（字符串，可选，'system'表示系统级，默认'bot'）"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    try:
        server_id = str(payload.get("server_id") or "").strip()
        if server_id:
            existing_server = get_mcp_server(database_path, server_id)
            if existing_server is None:
                raise NotFoundError("MCP server 未找到")
            usage = _collect_mcp_bot_usage(database_path, [server_id]).get(server_id)
            _assert_mcp_edit_allowed(existing_server, payload, usage)
        config = payload.get("config") or {}
        if str(payload.get("server_type") or config.get("transport") or "stdio") == "stdio":
            _validate_stdio_command(
                str(config.get("command") or ""),
                config.get("args") if isinstance(config.get("args"), list) else [],
            )
        server = upsert_mcp_server(database_path, payload)
        usage_map = _collect_mcp_bot_usage(database_path, [str(server.get("server_id") or "").strip()])
        return {
            "ok": True,
            "server": _enrich_bot_bound_item(server, usage_map.get(str(server.get("server_id") or "").strip())),
        }
    except (NotFoundError, ValidationError):
        raise
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


@router.delete("/servers/{server_id}", summary="删除MCP服务器", description="删除指定的MCP服务器配置，已被Bot挂载的无法删除")
def delete_mcp_server_api(
    request: Request,
    server_id: str = FastAPIPath(..., description="MCP服务器ID"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_admin(request)
    usage = _collect_mcp_bot_usage(database_path, [server_id]).get(server_id)
    if usage and usage["mounted_bot_count"] > 0:
        raise ValidationError(
            f"MCP [{usage['item_label']}] 已被 Bot [{', '.join(usage['mounted_bot_names'])}] 挂载，无法删除",
        )
    success = delete_mcp_server(database_path, server_id)
    if not success:
        raise NotFoundError("MCP server 未找到")
    return {"ok": True, "deleted": True}


@router.post("/servers/{server_id}/toggle", summary="切换MCP服务器启用状态", description="启用或禁用MCP服务器，已被Bot挂载的无法禁用")
def toggle_mcp_server_api(
    request: Request,
    server_id: str = FastAPIPath(..., description="MCP服务器ID"),
    payload: dict[str, Any] = Body(..., description="包含is_active字段的参数：is_active（布尔，true=启用，false=禁用）"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    is_active = bool(payload.get("is_active", False))
    try:
        if not is_active:
            usage = _collect_mcp_bot_usage(database_path, [server_id]).get(server_id)
            if usage and usage["mounted_bot_count"] > 0:
                raise ValidationError(
                    f"MCP [{usage['item_label']}] 已被 Bot [{', '.join(usage['mounted_bot_names'])}] 挂载，无法禁用",
                )
        toggle_mcp_server(database_path, server_id, is_active)
        server = get_mcp_server(database_path, server_id)
        usage_map = _collect_mcp_bot_usage(database_path, [server_id])
        return {"ok": True, "server": _enrich_bot_bound_item(server, usage_map.get(server_id))}
    except (NotFoundError, ValidationError):
        raise
    except ValueError as exc:
        raise ValidationError(str(exc)) from exc


@router.post("/servers/import", summary="导入MCP服务器配置", description="批量导入MCP服务器配置，支持Claude Desktop格式")
def import_mcp_servers_api(
    request: Request,
    payload: dict[str, Any] = Body(..., description="包含mcpServers字段的配置对象：mcpServers（对象，key为服务器名，value为配置），scope（字符串，可选，'system'表示系统级）"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    try:
        mcp_servers = payload.get("mcpServers", {})
        if not mcp_servers or not isinstance(mcp_servers, dict):
            raise ValueError("无效格式，必须包含 mcpServers 对象")

        raw_scope = str(payload.get("scope") or "").strip().lower()
        scope = "system" if raw_scope == "system" else "bot"

        imported = []
        for name, config in mcp_servers.items():
            if not isinstance(config, dict):
                continue

            server_type = "stdio"
            if "transport" in config:
                server_type = str(config.get("transport", "stdio"))
            elif "type" in config:
                server_type = str(config.get("type", "stdio"))
            elif "command" in config:
                server_type = "stdio"
            elif "url" in config:
                server_type = "http"

            if server_type == "stdio":
                _validate_stdio_command(
                    str(config.get("command") or ""),
                    config.get("args") if isinstance(config.get("args"), list) else [],
                )

            server = upsert_mcp_server(database_path, {
                "name": name,
                "server_type": server_type,
                "config": config,
                "is_active": False,
                "scope": scope,
            })
            imported.append(server)

        return {"ok": True, "imported": imported}
    except (NotFoundError, ValidationError):
        raise
    except Exception as exc:
        raise ValidationError(str(exc)) from exc


@router.post("/servers/{server_id}/test-connection", summary="测试MCP服务器连接", description="测试MCP服务器连接并获取可用工具列表")
async def test_mcp_server_connection(
    request: Request,
    server_id: str = FastAPIPath(..., description="MCP服务器ID"),
    database_path: Path = Depends(get_database_path),
) -> dict[str, Any]:
    require_non_guest(request)
    try:
        server = get_mcp_server(database_path, server_id)
        if not server:
            raise NotFoundError("MCP server 未找到")

        config = server.get("config", {})
        server_type = server.get("server_type", "stdio")

        test_settings = Settings(
            agent=AgentSettings(
                mcp=MCPSettings(
                    enabled=True,
                    servers={server['name']: config},
                ),
            ),
        )

        try:
            from langchain_mcp_adapters.client import MultiServerMCPClient
        except ImportError as exc:
            raise RuntimeError("langchain-mcp-adapters is not installed.") from exc

        client = MultiServerMCPClient(test_settings.agent.mcp.servers)
        tools = await client.get_tools()

        result = []
        for tool in tools:
            result.append({
                "name": str(getattr(tool, "name", "")),
                "description": str(getattr(tool, "description", "")),
                "args_schema": _schema_to_jsonable(getattr(tool, "args_schema", None)),
            })

        upsert_mcp_server(database_path, {
            "server_id": server_id,
            "name": server["name"],
            "server_type": server_type,
            "config": config,
            "tools": result,
            "is_active": server.get("is_active", False),
        })

        return {
            "ok": True,
            "tools": result,
            "tool_count": len(result),
        }
    except NotFoundError:
        raise
    except Exception as exc:
        raise ValidationError(f"连接测试失败: {str(exc)}") from exc
