from __future__ import annotations

"""运行时工具选择模块，处理 Skill 脚本、MCP 工具和内置工具的选择与构建。"""

import ast
import asyncio
from contextvars import ContextVar
from dataclasses import dataclass
import json
import os
import re
import shlex
import sys
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field

from app.config_loader import Settings
from app.yaml_config import get_yaml_config
from app.db.core import connect_database
from app.exceptions import DependencyError
from app.utils import default_database_path
from app.skills_store import build_skill_full_context, scan_skills

_current_chat_id: ContextVar[str] = ContextVar("_current_chat_id", default="")
_current_bot_key: ContextVar[str] = ContextVar("_current_bot_key", default="")
_current_project_root: ContextVar[str] = ContextVar("_current_project_root", default="")
_current_trace_id: ContextVar[str] = ContextVar("_current_trace_id", default="")
_current_call_type: ContextVar[str] = ContextVar("_current_call_type", default="")


def _cfg(dot_path: str, default: Any = None) -> Any:
    return get_yaml_config().get(dot_path, default)


class _SkillScriptToolInput(BaseModel):
    arguments: str = Field(
        default="",
        description=(
            "传给脚本的命令行参数，保持 CLI 格式，例如 "
            "`--trace-id 123 --jsessionid abc`。留空表示不传额外参数。"
        ),
    )
    timeout_seconds: int = Field(
        default=60,
        ge=1,
        le=300,
        description="脚本执行超时时间，单位秒。",
    )


@dataclass(frozen=True)
class RuntimeToolSelection:
    """运行时工具选择结果，包含选中的工具列表、Skill 上下文、诊断信息和提示词指令。"""

    tools: list[Any]
    skill_context: str
    diagnostics: list[str]
    prompt_instructions: list[str]


_MCP_TOOL_SCORE_THRESHOLD = 5
_MCP_EXPLICIT_SCORE_THRESHOLD = 2
_MCP_EXPLICIT_MAX_TOOLS = 12
_MCP_EXPLICIT_FALLBACK_TOOLS = 6
_SKILL_SCORE_THRESHOLD = 3
_MAX_BOT_SKILLS = 6
_MAX_SYSTEM_SKILLS = 6
_INTERNAL_MEMORY_SKILL_NAMES = {"memory-reader", "memory_reader"}
_NOTIFY_SKILL_NAMES = {"notify-me", "notify_me"}
_EXECUTED_SKILL_TOOLS_BY_TRACE: set[tuple[str, str, str]] = set()
_LAST_NOTIFY_TRACE_ID: str | None = None

def _collect_builtin_tools(settings: Settings) -> list[dict[str, Any]]:
    provider = settings.agent.providers.get(settings.agent.provider)
    if not provider or not provider.built_in_tools:
        return []
    if provider.type != "openai":
        return []
    return list(provider.built_in_tools)


async def select_runtime_tools(
    settings: Settings,
    *,
    project_root: Path | None = None,
    user_input_text: str = "",
    expanded_terms: list[str] | None = None,
) -> RuntimeToolSelection:
    diagnostics: list[str] = []
    prompt_instructions: list[str] = []
    database_path = default_database_path(project_root)

    # 有 LLM 扩展速查词时用速查词，否则用原查询
    match_text = " ".join(expanded_terms) if expanded_terms else user_input_text

    mounted_mcp_tools = await _build_mcp_tools(settings, database_path=database_path)
    selected_mcp_tools, mcp_diagnostics = _select_mcp_tools(
        mounted_mcp_tools,
        settings=settings,
        user_input_text=match_text,
        explicit_text=_build_explicit_tool_selection_text(settings, match_text),
    )
    prompt_instructions.extend(_build_mcp_prompt_instructions(selected_mcp_tools))
    system_prompt_text = str(getattr(settings.agent, "system_prompt", "") or "").strip()
    selected_skill_names, skill_context_names, skill_prompt_instructions, skill_diagnostics = _select_mounted_skill_names(
        settings,
        project_root=project_root,
        user_input_text=match_text,
        bot_prompt_text=system_prompt_text,
    )
    prompt_instructions.extend(skill_prompt_instructions)
    diagnostics.extend(mcp_diagnostics)
    diagnostics.extend(skill_diagnostics)
    diagnostics.append(
        f"selected_counts=mcp_tools:{len(selected_mcp_tools)},skills:{len(selected_skill_names)},skill_context:{len(skill_context_names)}"
    )

    tools: list[Any] = []
    tools.extend(selected_mcp_tools)
    tools.extend(
        _build_skill_script_tools(
            settings,
            project_root=project_root,
            selected_names=selected_skill_names,
        )
    )

    builtin_tools = _collect_builtin_tools(settings)
    if builtin_tools:
        tools.extend(builtin_tools)
        diagnostics.append(f"builtin_tools:{len(builtin_tools)}")

    skill_context = ""
    if project_root is not None and skill_context_names:
        skill_context = _build_selected_skill_context(
            project_root,
            prompt_skill_names=skill_context_names,
            tool_skill_names=selected_skill_names,
        )

    return RuntimeToolSelection(
        tools=tools,
        skill_context=skill_context,
        diagnostics=diagnostics,
        prompt_instructions=prompt_instructions,
    )


async def select_runtime_tools_for_task(
    settings: Settings,
    *,
    project_root: Path | None = None,
    user_input_text: str = "",
    force_skill_names: list[str] | None = None,
    force_mcp_server_ids: list[str] | None = None,
) -> RuntimeToolSelection:
    """专门为 bot_task 设计的工具选择函数，强制注入用户指定的 Skill 和 MCP"""
    diagnostics: list[str] = []
    prompt_instructions: list[str] = []
    database_path = default_database_path(project_root)

    # 处理 MCP 服务器选择
    # 如果 force_mcp_server_ids 不为 None，则只保留指定的 MCP 服务器
    original_servers = settings.agent.mcp.servers or {}
    forced_mcp_servers: dict[str, Any] = {}
    force_all_mcp_tools = False
    if force_mcp_server_ids is None:
        forced_mcp_servers = dict(original_servers)
        force_all_mcp_tools = True
    else:
        requested_mcp_servers = _merge_names([str(item or "").strip() for item in force_mcp_server_ids])
        forced_mcp_servers, unmatched_mcp_servers = _resolve_forced_mcp_servers(
            original_servers,
            requested_mcp_servers,
            database_path=database_path,
        )
        force_all_mcp_tools = bool(forced_mcp_servers)
        if requested_mcp_servers:
            diagnostics.append("forced_mcp_requested=" + ",".join(requested_mcp_servers))
        if unmatched_mcp_servers:
            diagnostics.append("unmatched_mcp_servers=" + ",".join(unmatched_mcp_servers))
    
    # 构建 MCP 工具（使用强制选择的服务器）
    # 使用 deepcopy 而不是 model_copy
    import copy
    temp_settings = copy.deepcopy(settings)
    temp_settings.agent.mcp.servers = forced_mcp_servers
    temp_settings.agent.mcp.enabled = bool(forced_mcp_servers)
    mounted_mcp_tools = await _build_mcp_tools(temp_settings, database_path=database_path)
    if force_all_mcp_tools:
        selected_mcp_tools = mounted_mcp_tools
        mcp_diagnostics = [
            "forced_mcp_servers="
            + (",".join(forced_mcp_servers.keys()) if forced_mcp_servers else "<none>")
            + f",mcp_tools={len(selected_mcp_tools)}"
        ]
    else:
        selected_mcp_tools, mcp_diagnostics = _select_mcp_tools(
            mounted_mcp_tools,
            settings=temp_settings,
            user_input_text=user_input_text,
            explicit_text=user_input_text,
        )
    prompt_instructions.extend(_build_mcp_prompt_instructions(selected_mcp_tools))
    diagnostics.extend(mcp_diagnostics)

    # 处理 Skill 选择
    # 先获取所有已挂载的技能
    all_mounted_skills: list[dict[str, Any]] = []
    enabled_mounted_skills: list[dict[str, Any]] = []
    if project_root:
        all_mounted_skills = scan_skills(project_root, None)
        enabled_mounted_skills = [
            skill
            for skill in scan_skills(project_root, settings.agent.skills.enabled)
            if bool(skill.get("enabled")) and not _is_internal_memory_skill(skill)
        ]
    # 强制选择的技能
    selected_skill_names: list[str] = []
    if force_skill_names:
        # 从所有技能中找出名称匹配的
        for skill in all_mounted_skills:
            skill_name = str(skill.get("name") or "").strip()
            if skill_name in force_skill_names:
                selected_skill_names.append(skill_name)
    if force_skill_names is None:
        explicit_skill_names = _detect_explicit_skill_requests(
            user_input_text,
            [
                skill for skill in all_mounted_skills
                if not _is_internal_memory_skill(skill)
            ],
        )
        scored_skill_names = [
            str(skill.get("name") or "").strip()
            for skill in _select_active_skills(
                user_input_text,
                enabled_mounted_skills,
                allow_explicit=False,
                limit=_MAX_BOT_SKILLS + _MAX_SYSTEM_SKILLS,
            )
        ]
        selected_skill_names = _merge_skill_names(
            selected_skill_names,
            explicit_skill_names,
            scored_skill_names,
        )
    # 添加 notify-me 技能用于通知结果（只追加一个）
    has_notify_me = any(name.lower() in _NOTIFY_SKILL_NAMES for name in selected_skill_names)
    if not has_notify_me:
        selected_skill_names.append("notify-me")
    
    # 构建 skill context（包含所有选中技能的 context）
    skill_context_names = selected_skill_names.copy()
    selected_tool_skill_names = [
        str(skill.get("name") or "").strip()
        for skill in all_mounted_skills
        if str(skill.get("name") or "").strip() in selected_skill_names and bool(skill.get("has_scripts"))
    ]
    prompt_instructions.extend(_build_skill_prompt_instructions(selected_tool_skill_names))
    
    # 添加强制调用的提示指令
    mcp_tool_names: list[str] = []
    for mcp_tool in selected_mcp_tools:
        if hasattr(mcp_tool, "name"):
            mcp_tool_names.append(str(getattr(mcp_tool, "name")))
    if mcp_tool_names:
        prompt_instructions.append(
            "本轮任务已选择 MCP 工具候选："
            + "、".join(mcp_tool_names)
            + "。必须按任务需要至少调用其中一个合适的 MCP 工具获取外部数据，不要只调用 Skill。"
        )
    skill_names_to_force: list[str] = []
    for skill_name in selected_skill_names:
        skill_names_to_force.append(skill_name)
    if skill_names_to_force:
        prompt_instructions.append(
            f"本轮任务必须调用以下 Skill 工具：{'、'.join(skill_names_to_force)}。"
            "其中 `notify-me` 是任务完成通知工具，必须在得到实际结果后调用。"
        )
    diagnostics.append(f"forced_skill_names={selected_skill_names},skill_context={len(skill_context_names)}")

    tools: list[Any] = []
    tools.extend(selected_mcp_tools)
    tools.extend(
        _build_skill_script_tools(
            settings,
            project_root=project_root,
            selected_names=selected_skill_names,
        )
    )

    builtin_tools = _collect_builtin_tools(settings)
    if builtin_tools:
        tools.extend(builtin_tools)
        diagnostics.append(f"builtin_tools:{len(builtin_tools)}")

    skill_context = ""
    if project_root is not None and skill_context_names:
        skill_context = _build_selected_skill_context(
            project_root,
            prompt_skill_names=skill_context_names,
            tool_skill_names=selected_skill_names,
        )

    return RuntimeToolSelection(
        tools=tools,
        skill_context=skill_context,
        diagnostics=diagnostics,
        prompt_instructions=prompt_instructions,
    )


def _resolve_forced_mcp_servers(
    original_servers: dict[str, Any],
    requested_servers: list[str],
    *,
    database_path: Path,
) -> tuple[dict[str, Any], list[str]]:
    requested = {str(item or "").strip() for item in requested_servers if str(item or "").strip()}
    if not requested:
        return {}, []

    forced: dict[str, Any] = {}
    matched: set[str] = set()

    for name, config in (original_servers or {}).items():
        server_name = str(name or "").strip()
        server_id = str(config.get("server_id", "")).strip() if isinstance(config, dict) else ""
        if server_name in requested or (server_id and server_id in requested):
            forced[server_name] = config
            matched.add(server_name)
            if server_id:
                matched.add(server_id)

    try:
        with connect_database(database_path) as conn:
            rows = conn.execute(
                """
                SELECT server_id, name, config_json
                FROM mcp_server_config
                WHERE is_active = 1
                """
            ).fetchall()
    except Exception:
        rows = []

    for row in rows:
        server_id = str(row["server_id"] or "").strip()
        server_name = str(row["name"] or "").strip()
        if not server_name or (server_id not in requested and server_name not in requested):
            continue

        if server_name not in forced:
            try:
                config = json.loads(str(row["config_json"] or "{}"))
            except Exception:
                config = {}
            if isinstance(config, dict) and config:
                forced[server_name] = config
        matched.add(server_name)
        if server_id:
            matched.add(server_id)

    unmatched = [item for item in requested_servers if item not in matched]
    return forced, unmatched


async def _build_mcp_tools(settings: Settings, *, database_path: Path) -> list[Any]:
    if not settings.agent.mcp.enabled or not settings.agent.mcp.servers:
        return []

    try:
        from langchain_mcp_adapters.client import MultiServerMCPClient
    except ImportError as exc:  # pragma: no cover
        raise DependencyError("langchain-mcp-adapters 未安装。") from exc

    client = MultiServerMCPClient(settings.agent.mcp.servers)
    tools = list(await client.get_tools())
    _attach_mcp_tool_metadata(tools, database_path=database_path, max_tool_description_chars=settings.agent.skills.max_tool_description_chars)
    return _wrap_tools_for_safe_execution(
        tools,
        timeout_seconds=max(1, int(settings.agent.timeout_seconds or _cfg("agent.timeout_seconds", 60))),
    )


def _wrap_tools_for_safe_execution(tools: list[Any], *, timeout_seconds: int) -> list[Any]:
    wrapped_tools: list[Any] = []
    for tool in tools:
        wrapped_tools.append(_wrap_tool_for_safe_execution(tool, timeout_seconds=timeout_seconds))
    return wrapped_tools


def _wrap_tool_for_safe_execution(tool: Any, *, timeout_seconds: int) -> Any:
    metadata = dict(getattr(tool, "metadata", {}) or {})
    if metadata.get("safe_execution_wrapper"):
        return tool
    if metadata.get("source") == "skill_script":
        return tool
    args_schema = getattr(tool, "args_schema", None)
    if args_schema is None:
        return tool
    try:
        from langchain_core.tools import StructuredTool
    except ImportError:
        return tool

    tool_name = str(getattr(tool, "name", "") or "tool")
    description = str(getattr(tool, "description", "") or "")
    safe_timeout = max(1, int(timeout_seconds or 60))

    async def _runner(
        *,
        _tool: Any = tool,
        _tool_name: str = tool_name,
        _timeout_seconds: int = safe_timeout,
        **kwargs: Any,
    ) -> Any:
        try:
            return await asyncio.wait_for(_tool.ainvoke(kwargs), timeout=_timeout_seconds)
        except asyncio.CancelledError:
            raise
        except asyncio.TimeoutError:
            return _tool_error_payload(
                tool_name=_tool_name,
                error_type="tool_timeout",
                message="Tool call timed out.",
                detail=f"{_tool_name} timed out after {_timeout_seconds} seconds.",
                timeout_seconds=_timeout_seconds,
            )
        except Exception as exc:
            return _tool_error_payload(
                tool_name=_tool_name,
                error_type="tool_exception",
                message="Tool call failed before returning a result.",
                detail=_format_exception_detail(exc),
            )

    wrapped = StructuredTool.from_function(
        coroutine=_runner,
        name=tool_name,
        description=description,
        args_schema=args_schema,
        handle_validation_error=lambda exc, _tool_name=tool_name: _tool_error_text(
            tool_name=_tool_name,
            error_type="tool_argument_validation_error",
            message="Tool arguments failed schema validation.",
            detail=_format_exception_detail(exc),
        ),
    )
    metadata["safe_execution_wrapper"] = True
    metadata["wrapped_tool_name"] = tool_name
    object.__setattr__(wrapped, "metadata", metadata)
    return wrapped


def _build_skill_script_tools(
    settings: Settings,
    *,
    project_root: Path | None,
    selected_names: list[str] | None = None,
) -> list[Any]:
    if project_root is None:
        return []
    if selected_names is None and not settings.agent.skills.enabled:
        return []

    try:
        from langchain_core.tools import StructuredTool
    except ImportError as exc:  # pragma: no cover
        raise DependencyError("langchain-core 未安装，无法加载本地 Skill 脚本工具。") from exc

    enabled_source = settings.agent.skills.enabled if selected_names is None else selected_names
    enabled = set(enabled_source)
    tools: list[Any] = []
    for skill in scan_skills(project_root, list(enabled)):
        if skill["name"] not in enabled:
            continue
        script_files = skill.get("script_files") or []
        if not script_files:
            continue

        skill_root = Path(str(skill["skill_root"]))
        for relative_script_path in script_files:
            script_path = skill_root / str(relative_script_path)
            if not script_path.exists() or not script_path.is_file():
                continue

            tool_name = _build_skill_script_tool_name(str(skill["name"]), str(relative_script_path))
            description = _build_skill_script_tool_description(
                skill, relative_script_path, script_path,
                max_tool_description_chars=settings.agent.skills.max_tool_description_chars,
            )

            async def _runner(
                arguments: str = "",
                timeout_seconds: int = 60,
                *,
                _skill_name: str = str(skill["name"]),
                _script_path: Path = script_path,
                _skill_root: Path = skill_root,
            ) -> Any:
                try:
                    return await _run_skill_script(
                        skill_name=_skill_name,
                        skill_root=_skill_root,
                        script_path=_script_path,
                        arguments=arguments,
                        timeout_seconds=timeout_seconds,
                    )
                except asyncio.CancelledError:
                    raise
                except Exception as exc:
                    return _tool_error_payload(
                        tool_name=_skill_name,
                        error_type="skill_tool_exception",
                        message="Skill tool failed before returning a result.",
                        detail=_format_exception_detail(exc),
                        script_path=str(_script_path),
                    )

            tool = StructuredTool.from_function(
                coroutine=_runner,
                name=tool_name,
                description=description,
                args_schema=_SkillScriptToolInput,
                handle_validation_error=lambda exc, _tool_name=tool_name: _tool_error_text(
                    tool_name=_tool_name,
                    error_type="tool_argument_validation_error",
                    message="Tool arguments failed schema validation.",
                    detail=_format_exception_detail(exc),
                ),
            )
            metadata = dict(getattr(tool, "metadata", {}) or {})
            metadata.update(
                {
                    "source": "skill_script",
                    "skill_name": str(skill["name"]),
                    "script_path": str(script_path.resolve()),
                    "script_mtime_ns": script_path.stat().st_mtime_ns,
                }
            )
            object.__setattr__(tool, "metadata", metadata)
            tools.append(tool)

    return tools


def _select_mcp_tools(
    mounted_tools: list[Any],
    *,
    settings: Settings,
    user_input_text: str,
    explicit_text: str = "",
) -> tuple[list[Any], list[str]]:
    if not mounted_tools:
        return [], ["selected_mcp_tools=<none>"]

    explicit_query = explicit_text or user_input_text
    explicit_server_names = _detect_explicit_server_requests(
        explicit_query,
        list(settings.agent.mcp.servers.keys()),
    )
    explicit_tool_names = _detect_explicit_mcp_tool_requests(explicit_query, mounted_tools)
    if explicit_server_names:
        server_tools = [
            tool for tool in mounted_tools
            if str((getattr(tool, "metadata", {}) or {}).get("server_name", "")) in explicit_server_names
        ]
        ranked: list[tuple[int, Any]] = []
        for tool in server_tools:
            score = _score_keyword_overlap(
                user_input_text,
                str(getattr(tool, "name", "")),
                str(getattr(tool, "description", "")),
                str((getattr(tool, "metadata", {}) or {}).get("catalog_description", "")),
            )
            if score >= _MCP_EXPLICIT_SCORE_THRESHOLD:
                ranked.append((score, tool))
        if ranked:
            ranked.sort(key=lambda item: (-item[0], str(getattr(item[1], "name", "")).lower()))
            selected = _merge_mcp_tools(
                _tools_by_names(mounted_tools, explicit_tool_names),
                [tool for _, tool in ranked[:_MCP_EXPLICIT_MAX_TOOLS]],
            )
        else:
            selected = _merge_mcp_tools(
                _tools_by_names(mounted_tools, explicit_tool_names),
                server_tools[:_MCP_EXPLICIT_FALLBACK_TOOLS],
            )
        return selected, [
            "selected_mcp_servers="
            + (", ".join(explicit_server_names) if explicit_server_names else "<none>"),
            "explicit_mcp_tools="
            + (", ".join(explicit_tool_names) if explicit_tool_names else "<none>"),
        ]
    if explicit_tool_names:
        selected = _tools_by_names(mounted_tools, explicit_tool_names)
        return selected, [
            "selected_mcp_tools="
            + (", ".join(str(getattr(tool, "name", "")) for tool in selected) if selected else "<none>"),
            "explicit_mcp_tools=" + ", ".join(explicit_tool_names),
        ]

    ranked: list[tuple[int, Any]] = []
    for tool in mounted_tools:
        score = _score_keyword_overlap(
            user_input_text,
            str(getattr(tool, "name", "")),
            str((getattr(tool, "metadata", {}) or {}).get("server_name", "")),
            str(getattr(tool, "description", "")),
            str((getattr(tool, "metadata", {}) or {}).get("catalog_description", "")),
        )
        if score >= _MCP_TOOL_SCORE_THRESHOLD:
            ranked.append((score, tool))

    ranked.sort(key=lambda item: (-item[0], str(getattr(item[1], "name", "")).lower()))
    selected = [tool for _, tool in ranked[:8]]
    diagnostics = [
        "selected_mcp_tools="
        + (", ".join(str(getattr(tool, "name", "")) for tool in selected) if selected else "<none>")
    ]
    return selected, diagnostics


def _build_mcp_prompt_instructions(selected_tools: list[Any]) -> list[str]:
    if not selected_tools:
        return []

    tool_names: list[str] = []
    for tool in selected_tools:
        name = str(getattr(tool, "name", "")).strip()
        if not name:
            continue
        tool_names.append(name)

    if not tool_names:
        return []

    instructions: list[str] = [
        "本轮候选 MCP 工具：" + "、".join(tool_names) + "。按用户任务需要调用，避免重复调用。",
    ]
    return instructions


def _build_explicit_tool_selection_text(settings: Settings, user_input_text: str) -> str:
    bot_prompt = str(getattr(settings.agent, "system_prompt", "") or "").strip()
    user_text = str(user_input_text or "").strip()
    return "\n\n".join(part for part in [user_text, bot_prompt] if part)


def _select_mounted_skill_names(
    settings: Settings,
    *,
    project_root: Path | None,
    user_input_text: str,
    bot_prompt_text: str = "",
) -> tuple[list[str], list[str], list[str], list[str]]:
    if project_root is None or not settings.agent.skills.enabled:
        return [], [], [], ["selected_skills=<none>"]

    mounted_skills = [
        skill
        for skill in scan_skills(project_root, settings.agent.skills.enabled)
        if bool(skill.get("enabled")) and not _is_internal_memory_skill(skill)
    ]
    prompt_instructions: list[str] = []
    all_skills = [
        skill for skill in scan_skills(project_root)
        if not _is_internal_memory_skill(skill)
    ]
    # Bot 提示词只用于显式 Skill 点名，不参与泛化关键词评分。
    requested_skills = _merge_skill_names(
        _detect_explicit_skill_requests(user_input_text, all_skills),
        _detect_explicit_skill_requests(bot_prompt_text, all_skills),
    )
    mounted_names = [str(skill["name"]) for skill in mounted_skills]
    unavailable = [name for name in requested_skills if name not in mounted_names]
    if unavailable:
        prompt_instructions.append(
            "用户或 Bot 指令提到了未挂载 Skill："
            + "、".join(unavailable)
            + "。禁止假装已启用这些 Skill；如确实需要，应明确说明当前 Bot 未挂载。"
        )
    requested_set = set(requested_skills)
    explicit_skills = [
        skill for skill in mounted_skills
        if str(skill.get("name") or "").strip() in requested_set
    ]
    bot_scoped_skills = [
        skill for skill in mounted_skills
        if str(skill.get("scope") or "bot") != "system"
    ]
    system_scoped_skills = [
        skill for skill in mounted_skills
        if str(skill.get("scope") or "bot") == "system"
    ]
    active_skills = _merge_skills(
        explicit_skills,
        _select_active_skills(user_input_text, bot_scoped_skills, allow_explicit=False, limit=_MAX_BOT_SKILLS),
        _select_active_skills(user_input_text, system_scoped_skills, allow_explicit=False, limit=_MAX_SYSTEM_SKILLS),
        [skill for skill in system_scoped_skills if bool(skill.get("always_active")) and not _is_internal_memory_skill(skill)],
    )
    selected_tool_skills = [
        str(skill.get("name") or "").strip()
        for skill in active_skills
        if bool(skill.get("has_scripts")) and _should_expose_skill_tool(skill, requested_set)
    ]
    selected_prompt_skills = [
        str(skill.get("name") or "").strip()
        for skill in active_skills
    ]
    diagnostics = [
        "selected_skills="
        + (", ".join(str(skill.get("name") or "") for skill in active_skills) if active_skills else "<none>")
    ]
    diagnostics.append(
        "selected_skill_tools="
        + (", ".join(selected_tool_skills) if selected_tool_skills else "<none>")
    )
    prompt_instructions.extend(_build_skill_prompt_instructions(selected_tool_skills))
    return selected_tool_skills, selected_prompt_skills, prompt_instructions, diagnostics


def _build_selected_skill_context(
    project_root: Path,
    *,
    prompt_skill_names: list[str],
    tool_skill_names: list[str],
) -> str:
    if not prompt_skill_names:
        return ""

    requested_names = {
        str(name or "").strip()
        for name in prompt_skill_names
        if str(name or "").strip()
    }
    if not requested_names:
        return ""

    full_context = build_skill_full_context(project_root, list(requested_names))
    parts: list[str] = []
    if full_context:
        parts.append(full_context)

    return "\n\n".join(part for part in parts if part).strip()


def _should_expose_skill_tool(skill: dict[str, Any], explicit_names: set[str]) -> bool:
    name = str(skill.get("name") or "").strip()
    if not name:
        return False
    if str(skill.get("scope") or "bot") != "system":
        return True
    normalized_name = name.lower()
    return name in explicit_names or normalized_name in _NOTIFY_SKILL_NAMES


def _merge_skills(*groups: list[dict[str, Any]]) -> list[dict[str, Any]]:
    merged: list[dict[str, Any]] = []
    seen: set[str] = set()
    for group in groups:
        for skill in group:
            name = str(skill.get("name") or "").strip()
            if not name or name in seen:
                continue
            merged.append(skill)
            seen.add(name)
    return merged


def _build_skill_prompt_instructions(tool_skill_names: list[str]) -> list[str]:
    if not tool_skill_names:
        return []

    instructions = ["优先调用 Skill 工具: " + "、".join(tool_skill_names) + "。"]
    if any(name.lower() in _NOTIFY_SKILL_NAMES for name in tool_skill_names):
        instructions.append("`notify-me` 仅用于结果通知，单轮最多一次。")
    return instructions


def _normalize_match_text(value: str) -> str:
    return re.sub(r"\s+", "", str(value or "").strip().lower())


def _extract_match_tokens(value: str) -> list[str]:
    normalized = _normalize_match_text(value)
    if not normalized:
        return []

    tokens: set[str] = set()
    for token in re.findall(r"[a-z0-9_]{2,}", normalized):
        tokens.add(token)
        for fragment in re.findall(r"[a-z_]{2,}|\d{2,}", token):
            tokens.add(fragment)
    for block in re.findall(r"[\u4e00-\u9fff]{2,}", normalized):
        tokens.add(block)
        max_size = min(4, len(block))
        for size in range(2, max_size + 1):
            for index in range(0, len(block) - size + 1):
                tokens.add(block[index : index + size])
    return sorted(
        (token for token in tokens if token),
        key=len,
        reverse=True,
    )


def _score_keyword_overlap(query: str, *haystacks: str) -> int:
    query_normalized = _normalize_match_text(query)
    if not query_normalized:
        return 0

    score = 0
    for haystack in haystacks:
        normalized = _normalize_match_text(haystack)
        if not normalized:
            continue
        # 整体文本匹配：用户问题整体出现在 skill name/description 中
        if query_normalized in normalized:
            score += 6
        # skill name/description 整体出现在用户问题中
        if normalized in query_normalized:
            score += 6

    # token 级别匹配作为补充
    tokens = _extract_match_tokens(query_normalized)
    if tokens:
        for haystack in haystacks:
            normalized = _normalize_match_text(haystack)
            if not normalized:
                continue
            for token in tokens:
                if len(token) >= 2 and token in normalized:
                    score += 2 if len(token) <= 3 else 3
    return score


def _attach_mcp_tool_metadata(tools: list[Any], *, database_path: Path, max_tool_description_chars: int = 5000) -> None:
    catalog: dict[str, dict[str, str]] = {}
    try:
        with connect_database(database_path) as conn:
            rows = conn.execute(
                "SELECT name, tools_json FROM mcp_server_config"
            ).fetchall()
        for row in rows:
            server_name = str(row["name"] or "").strip()
            try:
                tool_items = json.loads(str(row["tools_json"] or "[]"))
            except Exception:
                tool_items = []
            for item in tool_items:
                if not isinstance(item, dict):
                    continue
                tool_name = str(item.get("name") or item.get("tool_name") or "").strip()
                if not tool_name:
                    continue
                catalog[tool_name] = {
                    "server_name": server_name,
                    "catalog_description": str(item.get("description") or "").strip(),
                }
    except Exception:
        catalog = {}

    for tool in tools:
        name = str(getattr(tool, "name", "")).strip()
        if not name:
            continue
        description = _truncate_text(str(getattr(tool, "description", "")), max_chars=max_tool_description_chars)
        metadata = dict(getattr(tool, "metadata", {}) or {})
        if name in catalog:
            metadata.update({k: v for k, v in catalog[name].items() if v})
        metadata["source"] = "mcp"
        try:
            object.__setattr__(tool, "metadata", metadata)
        except Exception:
            pass
        try:
            object.__setattr__(tool, "description", description)
        except Exception:
            pass





def _compact_json_value(value: Any, *, depth: int = 0) -> Any:
    if depth >= 4:
        return "[truncated depth]"
    if isinstance(value, dict):
        keys = list(value.keys())
        preferred = [
            "summary",
            "message",
            "result",
            "status",
            "title",
            "name",
            "id",
            "traceId",
            "trace_id",
            "error",
            "code",
        ]
        ordered_keys: list[Any] = []
        seen: set[Any] = set()
        for key in preferred + keys:
            if key in value and key not in seen:
                ordered_keys.append(key)
                seen.add(key)
        limited_keys = ordered_keys[:12]
        compacted = {
            str(key): _compact_json_value(value.get(key), depth=depth + 1)
            for key in limited_keys
        }
        if len(keys) > len(limited_keys):
            compacted["_truncated_keys"] = len(keys) - len(limited_keys)
        return compacted
    if isinstance(value, (list, tuple)):
        items = [_compact_json_value(item, depth=depth + 1) for item in list(value)[:8]]
        if len(value) > len(items):
            items.append(f"...[{len(value) - len(items)} more items]")
        return items
    if isinstance(value, str):
        return _compact_text_payload(value, max_chars=1200)
    return value


def _compact_text_payload(text: str, *, max_chars: int = 6000) -> str:
    normalized = str(text or "").strip()
    if not normalized:
        return ""

    for candidate in _json_candidates(normalized):
        try:
            payload = json.loads(candidate)
        except json.JSONDecodeError:
            continue
        rendered = json.dumps(_compact_json_value(payload), ensure_ascii=False, indent=2)
        if len(rendered) <= max_chars:
            return rendered
        return rendered[: max_chars - 18].rstrip() + "\n...[truncated]"

    if len(normalized) <= max_chars:
        return normalized
    return normalized[: max_chars - 18].rstrip() + "\n...[truncated]"


def _detect_explicit_server_requests(user_input_text: str, server_names: list[str]) -> list[str]:
    normalized_query = _normalize_match_text(user_input_text)
    if not normalized_query:
        return []
    explicit: list[str] = []
    for server_name in server_names:
        normalized_name = _normalize_match_text(server_name)
        if not normalized_name:
            continue
        if normalized_name in normalized_query:
            explicit.append(server_name)
    return explicit


def _detect_explicit_mcp_tool_requests(user_input_text: str, tools: list[Any]) -> list[str]:
    normalized_query = _normalize_match_text(user_input_text)
    if not normalized_query:
        return []
    explicit: list[str] = []
    for tool in tools:
        name = str(getattr(tool, "name", "") or "").strip()
        if not name:
            continue
        if _is_explicit_name_match(name, normalized_query):
            explicit.append(name)
    return _merge_names(explicit)


def _tools_by_names(tools: list[Any], names: list[str]) -> list[Any]:
    requested = set(names)
    return [
        tool for tool in tools
        if str(getattr(tool, "name", "") or "").strip() in requested
    ]


def _merge_mcp_tools(*groups: list[Any]) -> list[Any]:
    merged: list[Any] = []
    seen: set[str] = set()
    for group in groups:
        for tool in group:
            name = str(getattr(tool, "name", "") or "").strip()
            if not name or name in seen:
                continue
            merged.append(tool)
            seen.add(name)
    return merged


def _compact_match_text(value: str) -> str:
    return re.sub(r"[^a-z0-9\u4e00-\u9fff]+", "", str(value or "").strip().lower())


def _is_explicit_name_match(candidate: str, normalized_query: str) -> bool:
    """简单子串匹配：candidate 或其紧凑形式出现在 query 中即命中。"""
    normalized_candidate = _normalize_match_text(candidate)
    if normalized_candidate and normalized_candidate in normalized_query:
        return True
    compact_candidate = _compact_match_text(candidate)
    compact_query = _compact_match_text(normalized_query)
    return bool(compact_candidate and compact_candidate in compact_query)


def _detect_explicit_skill_requests(user_input_text: str, skills: list[dict[str, Any]]) -> list[str]:
    normalized_query = _normalize_match_text(user_input_text)
    if not normalized_query:
        return []
    explicit: list[str] = []
    for skill in skills:
        skill_name = str(skill.get("name") or "").strip()
        display_name = str(skill.get("display_name") or skill_name).strip()
        relative_path = str(skill.get("relative_path") or "").strip()
        folder_alias = Path(relative_path).parent.name if relative_path else ""
        for candidate in (skill_name, display_name, relative_path, folder_alias):
            if _is_explicit_name_match(candidate, normalized_query):
                explicit.append(skill_name)
                break
    return _merge_names(explicit)


def _merge_names(*groups: list[str]) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for group in groups:
        for name in group:
            normalized = str(name or "").strip()
            if not normalized or normalized in seen:
                continue
            merged.append(normalized)
            seen.add(normalized)
    return merged


def _merge_skill_names(*groups: list[str]) -> list[str]:
    return _merge_names(*groups)


def _is_internal_memory_skill(skill: dict[str, Any]) -> bool:
    return _is_internal_memory_skill_name(str(skill.get("name") or ""))


def _is_internal_memory_skill_name(name: str) -> bool:
    return str(name or "").strip().lower() in _INTERNAL_MEMORY_SKILL_NAMES


def _select_active_skills(
    user_input_text: str,
    mounted_skills: list[dict[str, Any]],
    *,
    allow_explicit: bool = True,
    limit: int = 4,
) -> list[dict[str, Any]]:
    if not mounted_skills:
        return []

    if allow_explicit:
        explicit = _detect_explicit_skill_requests(user_input_text, mounted_skills)
        if explicit:
            return [skill for skill in mounted_skills if str(skill.get("name") or "").strip() in explicit]

    ranked: list[tuple[int, dict[str, Any]]] = []
    for skill in mounted_skills:
        score = _score_keyword_overlap(
            user_input_text,
            str(skill.get("name") or ""),
            str(skill.get("display_name") or ""),
            str(skill.get("description") or ""),
            str(skill.get("relative_path") or ""),
        )
        if score >= _SKILL_SCORE_THRESHOLD:
            ranked.append((score, skill))
    ranked.sort(key=lambda item: (-item[0], str(item[1].get("name") or "").lower()))
    return [skill for _, skill in ranked[:limit]]


def _build_skill_script_tool_name(skill_name: str, relative_script_path: str) -> str:
    base = f"skill_{skill_name}_{Path(relative_script_path).stem}"
    normalized = re.sub(r"[^a-zA-Z0-9_]+", "_", base).strip("_").lower()
    return normalized or "skill_tool"


def _build_skill_script_tool_description(
    skill: dict[str, Any],
    relative_script_path: str,
    script_path: Path,
    *,
    max_tool_description_chars: int = 5000,
) -> str:
    parts = [
        f"执行 Skill [{skill['name']}] 的本地脚本 `{relative_script_path}`。",
    ]
    skill_description = str(skill.get("description") or "").strip()
    if skill_description:
        parts.append(_truncate_text(skill_description, max_chars=max_tool_description_chars))
    script_doc = _read_script_docstring(script_path)
    if script_doc:
        parts.append(f"脚本说明：{_truncate_text(script_doc, max_chars=max_tool_description_chars)}")
    parts.append("参数请按命令行格式放进 arguments 字段，不要包含 `python` 或脚本路径本身。")
    return _truncate_text(" ".join(parts), max_chars=max_tool_description_chars)


def _read_script_docstring(script_path: Path) -> str:
    try:
        source = script_path.read_text(encoding="utf-8")
    except OSError:
        return ""

    try:
        module = ast.parse(source)
    except SyntaxError:
        return ""

    docstring = ast.get_docstring(module) or ""
    return " ".join(docstring.strip().split())


def _close_unbalanced_shell_quotes(arguments: str) -> str:
    text = str(arguments or "")
    quote_char = ""
    escaped = False
    for char in text:
        if escaped:
            escaped = False
            continue
        if char == "\\":
            escaped = True
            continue
        if quote_char:
            if char == quote_char:
                quote_char = ""
            continue
        if char in {"'", '"'}:
            quote_char = char
    if quote_char:
        return text + quote_char
    return text


def _tool_error_payload(
    *,
    tool_name: str,
    error_type: str,
    message: str,
    detail: str = "",
    **extra: Any,
) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "ok": False,
        "error_type": error_type,
        "error": message,
        "tool_name": str(tool_name or ""),
        "recoverable": True,
    }
    if detail:
        payload["detail"] = detail[:4000]
    for key, value in extra.items():
        if value not in (None, "", [], {}):
            payload[key] = value
    return payload


def _tool_error_text(
    *,
    tool_name: str,
    error_type: str,
    message: str,
    detail: str = "",
    **extra: Any,
) -> str:
    return json.dumps(
        _tool_error_payload(
            tool_name=tool_name,
            error_type=error_type,
            message=message,
            detail=detail,
            **extra,
        ),
        ensure_ascii=False,
    )


def _format_exception_detail(exc: BaseException) -> str:
    return f"{exc.__class__.__name__}: {exc}"


async def _run_skill_script(
    *,
    skill_name: str,
    skill_root: Path,
    script_path: Path,
    arguments: str,
    timeout_seconds: int,
) -> Any:
    posix_mode = os.name != "nt"
    safe_arguments = _close_unbalanced_shell_quotes(arguments)
    try:
        cli_args = shlex.split(safe_arguments, posix=posix_mode) if safe_arguments.strip() else []
    except ValueError as exc:
        return _tool_error_payload(
            tool_name=skill_name,
            error_type="invalid_skill_arguments",
            message="Skill arguments parse failed. Check for unmatched quotes in the arguments field.",
            detail=str(exc),
            skill_name=skill_name,
            retry_hint="Call the skill again with valid CLI-style arguments and balanced quotes.",
        )

    trace_id_val = _current_trace_id.get("")
    normalized_skill_name = str(skill_name or "").strip().lower()
    if trace_id_val and normalized_skill_name in _NOTIFY_SKILL_NAMES:
        execution_key = (
            trace_id_val,
            normalized_skill_name,
            str(script_path.resolve()).lower(),
        )
        if execution_key in _EXECUTED_SKILL_TOOLS_BY_TRACE:
            return {
                "ok": True,
                "skipped": True,
                "reason": "同一 traceId 已调用过 notify-me，本次跳过以避免重复通知。",
                "trace_id": trace_id_val,
            }
        _EXECUTED_SKILL_TOOLS_BY_TRACE.add(execution_key)

    argv = [sys.executable, str(script_path)]
    argv.extend(cli_args)

    env = os.environ.copy()
    env["PYTHONIOENCODING"] = "utf-8"
    env["PYTHONUNBUFFERED"] = "1"

    chat_id_val = _current_chat_id.get("")
    bot_key_val = _current_bot_key.get("")
    project_root_val = _current_project_root.get("")
    call_type_val = _current_call_type.get("")
    if chat_id_val:
        env["CHAT_ID"] = chat_id_val
    if bot_key_val:
        env["BOT_KEY"] = bot_key_val
    if project_root_val:
        env["PROJECT_ROOT"] = project_root_val
    if trace_id_val:
        env["TRACE_ID"] = trace_id_val
    if call_type_val:
        env["CALL_TYPE"] = call_type_val
    if normalized_skill_name in _NOTIFY_SKILL_NAMES and call_type_val == "bot_task":
        env["NOTIFY_SKIP_RECORD"] = "1"

    try:
        process = await asyncio.create_subprocess_exec(
            *argv,
            cwd=str(skill_root),
            env=env,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE,
        )
    except Exception as exc:
        return _tool_error_payload(
            tool_name=skill_name,
            error_type="skill_start_failed",
            message="Skill script failed to start.",
            detail=_format_exception_detail(exc),
            script_path=str(script_path),
            cwd=str(skill_root),
        )

    try:
        stdout_bytes, stderr_bytes = await asyncio.wait_for(
            process.communicate(),
            timeout=timeout_seconds,
        )
    except asyncio.TimeoutError:
        try:
            process.kill()
        except ProcessLookupError:
            pass
        except Exception:
            pass
        try:
            await process.communicate()
        except Exception:
            pass
        return _tool_error_payload(
            tool_name=skill_name,
            error_type="skill_timeout",
            message="Skill script timed out.",
            detail=f"{script_path.name} timed out after {timeout_seconds} seconds.",
            script_path=str(script_path),
            timeout_seconds=timeout_seconds,
        )

    stdout_text = stdout_bytes.decode("utf-8", errors="replace").strip()
    stderr_text = stderr_bytes.decode("utf-8", errors="replace").strip()

    max_script_chars = _cfg("skills.max_script_output_chars")

    # 尝试解析 stdout 中的结构化 JSON（即使退出码非零）
    rendered = _pretty_render_script_output(stdout_text, max_chars=max_script_chars)
    is_structured_json = isinstance(rendered, dict) and rendered.get("schema")

    if process.returncode != 0 and not is_structured_json:
        return _tool_error_payload(
            tool_name=skill_name,
            error_type="skill_script_failed",
            message="Skill script exited with a non-zero status.",
            detail=(stderr_text or stdout_text)[:4000],
            exit_code=process.returncode,
            script_path=str(script_path),
            stdout=stdout_text[:2000],
            stderr=stderr_text[:2000],
        )

    if not stdout_text and stderr_text:
        return _tool_error_payload(
            tool_name=skill_name,
            error_type="skill_stderr_without_result",
            message="Skill script wrote stderr but returned no result.",
            detail=stderr_text[:4000],
            script_path=str(script_path),
            stderr=stderr_text[:2000],
        )

    if not stdout_text and not stderr_text:
        return _tool_error_payload(
            tool_name=skill_name,
            error_type="empty_tool_result",
            message="Skill script returned no output.",
            script_path=str(script_path),
            exit_code=process.returncode,
        )

    if stderr_text:
        if isinstance(rendered, dict):
            rendered["_stderr"] = stderr_text[:2000]
        elif isinstance(rendered, list):
            rendered.append({"_stderr": stderr_text[:2000]})
        else:
            rendered = {"result": rendered, "_stderr": stderr_text[:2000]}

    return rendered


def _pretty_render_script_output(text: str, *, max_chars: int = 8000) -> Any:
    stripped = text.strip()
    if not stripped:
        return ""

    for candidate in _json_candidates(stripped):
        try:
            payload = json.loads(candidate)
            compacted = _compact_skill_script_json_payload(payload)
            return compacted
        except json.JSONDecodeError:
            continue

    # 如果不是 JSON，直接返回截断后的字符串
    return stripped[:max_chars]


def _compact_skill_script_json_payload(payload: Any) -> Any:
    if isinstance(payload, dict) and str(payload.get("schema") or "").strip() == "trace_log_bot_decision/v1":
        decision = payload.get("decision") or {}
        issue = payload.get("issue_classification") or {}
        user_reply = payload.get("user_reply") or {}
        summary = payload.get("summary") or {}
        compacted_summary: dict[str, Any] = {}
        for key in ("module", "method", "hasError", "hasErrorNormalized"):
            value = summary.get(key)
            if value not in (None, "", []):
                compacted_summary[key] = value
        entry = summary.get("entry")
        if isinstance(entry, dict):
            compacted_summary["entry"] = {
                key: entry.get(key)
                for key in ("module", "method", "hasError", "hasErrorNormalized")
                if entry.get(key) not in (None, "", [])
            }
        return {
            "ok": bool(payload.get("ok", False)),
            "schema": str(payload.get("schema") or ""),
            "trace_id": str(payload.get("trace_id") or ""),
            "decision": {
                "status": str(decision.get("status") or ""),
                "severity": str(decision.get("severity") or ""),
                "notify_required": bool(decision.get("notify_required", False)),
                "can_reply_no_obvious_issue": bool(decision.get("can_reply_no_obvious_issue", False)),
                "reason": str(decision.get("reason") or ""),
            },
            "issue_classification": {
                "category": str(issue.get("category") or ""),
                "confidence": str(issue.get("confidence") or ""),
            },
            "user_reply": {
                "text": str(user_reply.get("text") or ""),
            },
            "notify_summary": _compact_text_payload(str(payload.get("notify_summary") or ""), max_chars=400),
            "summary": compacted_summary,
        }
    return _compact_json_value(payload)


def _json_candidates(text: str) -> list[str]:
    candidates = [text]
    markers = [
        "[JSON输出]",
        "[JSON_OUTPUT]",
        "[JSON_OUTPUT_START]",
    ]
    for marker in markers:
        index = text.rfind(marker)
        if index >= 0:
            candidates.append(text[index + len(marker):].strip())
    last_object = text.rfind("{")
    if last_object >= 0:
        candidates.append(text[last_object:].strip())
    return [candidate for candidate in candidates if candidate]


def _truncate_text(text: str, *, max_chars: int = 5000) -> str:
    compact = " ".join(str(text or "").split())
    if len(compact) <= max_chars:
        return compact
    return compact[:max_chars].rstrip() + "..."
