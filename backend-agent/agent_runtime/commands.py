from __future__ import annotations

"""系统命令分发模块，实现 Bot 命令（如 /help、/status 等）的注册与调度。"""

import asyncio
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path
from typing import Any, Callable, Coroutine

from app.logger import get_logger
from app.utils import CST

logger = get_logger(__name__)


@dataclass(slots=True, frozen=True)
class SystemCommand:
    """系统命令定义，包含命令关键词、别名、描述、处理函数和绑定要求。"""

    keyword: str
    aliases: tuple[str, ...]
    description: str
    handler: Callable[..., Coroutine[Any, Any, str]]
    require_bound: bool


SYSTEM_COMMANDS: dict[str, SystemCommand] = {}
_NO_PREFIX_COMMANDS: dict[str, SystemCommand] = {}


def register_command(command: SystemCommand) -> None:
    """注册一个系统命令，将其关键词和所有别名添加到命令注册表。"""
    SYSTEM_COMMANDS[command.keyword.lower()] = command
    for alias in command.aliases:
        SYSTEM_COMMANDS[alias.lower()] = command


def register_no_prefix_command(command: SystemCommand) -> None:
    _NO_PREFIX_COMMANDS[command.keyword.lower()] = command
    for alias in command.aliases:
        _NO_PREFIX_COMMANDS[alias.lower()] = command


def _strip_at_prefix(text: str) -> str:
    stripped = text.strip()
    while stripped.startswith("@"):
        space_idx = stripped.find(" ")
        if space_idx < 0:
            break
        stripped = stripped[space_idx:].strip()
    return stripped


def is_command_attempt(text: str) -> bool:
    return _strip_at_prefix(text).startswith("/")


def is_no_prefix_command(text: str) -> bool:
    return _strip_at_prefix(text).lower() in _NO_PREFIX_COMMANDS


def match_system_command(text: str) -> SystemCommand | None:
    stripped = _strip_at_prefix(text).lower()
    cmd = SYSTEM_COMMANDS.get(stripped)
    if cmd is not None:
        return cmd
    return _NO_PREFIX_COMMANDS.get(stripped)


async def dispatch_system_command(
    keyword: str,
    *,
    context: dict[str, Any] | None = None,
    is_bound: bool = False,
) -> str:
    """根据关键词分发系统命令，查找并执行对应的命令处理函数。"""
    cmd = SYSTEM_COMMANDS.get(keyword) or _NO_PREFIX_COMMANDS.get(keyword)
    if cmd is None:
        parts = keyword.split(None, 1)
        if len(parts) > 1:
            cmd = SYSTEM_COMMANDS.get(parts[0]) or _NO_PREFIX_COMMANDS.get(parts[0])
            if cmd is not None:
                context = dict(context or {})
                context["command_args"] = parts[1]
    if cmd is None:
        logger.warning("未知命令: %s", keyword, extra={"category": "command"})
        return "命令不存在"
    if cmd.require_bound and not is_bound:
        return "该命令仅限绑定者使用"
    return await cmd.handler(context=context or {})


async def _cmd_close_bot(context: dict[str, Any]) -> str:
    shutdown_callback = context.get("shutdown_callback")
    if shutdown_callback is not None:
        await shutdown_callback()
        return "Bot 正在关闭，已向活跃会话发送通知。"
    return "无法执行关闭操作。"


async def _cmd_shutdown(context: dict[str, Any]) -> str:
    await _set_awaiting_exit_confirm(context, True)
    return "本命令将结束所有还在运行的bot并关闭系统服务，请发送 /ok 来确认执行。"


async def _cmd_ok(context: dict[str, Any]) -> str:
    if not _get_awaiting_exit_confirm(context):
        return "没有待确认的操作。"
    await _set_awaiting_exit_confirm(context, False)
    await _trigger_system_exit(context)
    return "确认收到，正在关闭所有 Bot 并退出系统..."


def _get_awaiting_exit_confirm(context: dict[str, Any]) -> bool:
    return bool(context.get("awaiting_exit_confirm", False))


async def _set_awaiting_exit_confirm(context: dict[str, Any], value: bool) -> None:
    set_callback = context.get("set_awaiting_exit_confirm")
    if set_callback:
        set_callback(value)


async def _trigger_system_exit(context: dict[str, Any]) -> None:
    import httpx
    try:
        # 调用系统退出 API，走完整的退出流程
        async with httpx.AsyncClient(timeout=30.0) as client:
            await client.post("http://127.0.0.1:8765/api/exit")
    except Exception:
        pass


async def _cmd_status(context: dict[str, Any]) -> str:
    bot_status = context.get("bot_status") or {}
    bot_name = bot_status.get("bot_name", "未知")
    running = bot_status.get("running", False)
    bound = bot_status.get("bound", False)
    bound_name = bot_status.get("bound_chat_name", "")
    started_at = bot_status.get("started_at", "")
    active_conversations = bot_status.get("active_conversations", 0)

    if not running:
        return f"Bot【{bot_name}】当前状态：已停止"

    lines = [f"Bot【{bot_name}】当前状态：运行中"]
    if bound and bound_name:
        lines.append(f"绑定用户：{bound_name}")
    else:
        lines.append("绑定状态：未绑定")
    if started_at:
        try:
            start_ts = float(started_at)
            start_time = datetime.fromtimestamp(start_ts, tz=CST)
            uptime = datetime.now(CST) - start_time
            hours, remainder = divmod(int(uptime.total_seconds()), 3600)
            minutes, seconds = divmod(remainder, 60)
            lines.append(f"运行时长：{hours}小时{minutes}分钟")
        except (ValueError, OSError):
            lines.append(f"启动时间：{started_at}")
    lines.append(f"活跃会话数：{active_conversations}")
    return "\n".join(lines)


async def _cmd_usage(context: dict[str, Any]) -> str:
    from app.db.token_usage_store import get_token_usage_summary_by_bot, get_token_usage_summary
    from app.db.bot_store import get_bot_config

    database_path = context.get("database_path")
    bot_key = context.get("bot_key", "")
    if not database_path:
        return "无法查询消耗：缺少数据库路径"

    bot_name = "未知"
    if bot_key:
        bot = get_bot_config(database_path, bot_key)
        if bot:
            bot_name = bot.get("name", "未知")

    # 获取当前 Bot 的消耗（优先使用 bot_key）
    summary = get_token_usage_summary_by_bot(
        database_path, bot_key=bot_key,
    )
    today_tokens = summary.get("today_tokens", 0)
    today_input = summary.get("today_input_tokens", 0)
    today_output = summary.get("today_output_tokens", 0)
    total_tokens = summary.get("total_tokens", 0)
    total_input = summary.get("total_input_tokens", 0)
    total_output = summary.get("total_output_tokens", 0)

    all_summary = get_token_usage_summary(database_path)
    all_total_tokens = all_summary.get("total_tokens", 0)
    all_input_tokens = all_summary.get("input_tokens", 0)
    all_output_tokens = all_summary.get("output_tokens", 0)

    lines = [
        f"Bot名称：{bot_name}",
        f"今日消耗：{today_tokens:,}",
        f"  输入：{today_input:,} / 输出：{today_output:,}",
        f"单Bot累计：{total_tokens:,}",
        f"  输入：{total_input:,} / 输出：{total_output:,}",
        f"全部消耗：{all_total_tokens:,}",
        f"  输入：{all_input_tokens:,} / 输出：{all_output_tokens:,}",
    ]
    return "\n".join(lines)


register_command(SystemCommand(
    keyword="/关闭Bot",
    aliases=("/closebot",),
    description="关闭当前 Bot",
    handler=_cmd_close_bot,
    require_bound=True,
))

register_command(SystemCommand(
    keyword="/结束服务",
    aliases=("/shutdown",),
    description="结束服务（退出系统）",
    handler=_cmd_shutdown,
    require_bound=True,
))

register_command(SystemCommand(
    keyword="/ok",
    aliases=("/OK", "/Ok"),
    description="确认操作",
    handler=_cmd_ok,
    require_bound=True,
))

register_command(SystemCommand(
    keyword="/查看状态",
    aliases=("/status",),
    description="查看状态",
    handler=_cmd_status,
    require_bound=True,
))

register_command(SystemCommand(
    keyword="/查看消耗",
    aliases=("/usage",),
    description="查看消耗",
    handler=_cmd_usage,
    require_bound=True,
))


async def _cmd_transfer_human(context: dict[str, Any]) -> str:
    chat_id = context.get("chat_id", "")
    transfer_callback = context.get("transfer_human_callback")
    if transfer_callback is not None and chat_id:
        return await transfer_callback(chat_id)
    return "转人工功能暂不可用。"


register_no_prefix_command(SystemCommand(
    keyword="转人工",
    aliases=("转接人工", "人工客服", "转客服", "找人工"),
    description="转接人工客服",
    handler=_cmd_transfer_human,
    require_bound=False,
))


async def _cmd_memory_create(context: dict[str, Any]) -> str:
    command_args = context.get("command_args", "")
    original_text = context.get("original_text", "")

    text_to_remember = command_args.strip()
    if not text_to_remember:
        stripped = _strip_at_prefix(original_text)
        parts = stripped.split(None, 1)
        if len(parts) > 1:
            text_to_remember = parts[1].strip()

    if not text_to_remember:
        return "请提供要记忆的内容。\n用法：/记忆生成 <要记住的文本>"

    database_path = context.get("database_path")
    db_path = Path(database_path) if database_path else None
    if not db_path:
        return "无法创建记忆任务：缺少数据库路径"

    import json
    from app.db.task_store import create_one_time_task, trigger_task_now

    prompt_data = json.dumps(
        {"source_text": text_to_remember},
        ensure_ascii=False,
    )

    bot_key = str(context.get("bot_key", "") or "").strip()

    task = await asyncio.to_thread(
        create_one_time_task,
        db_path,
        name="记忆生成",
        description=f"用户显式记忆：{text_to_remember[:50]}",
        executor_kind="platform_agent",
        executor_id=bot_key,
        handler_name="explicit_memory",
        prompt_text=prompt_data,
        task_scope="system",
    )

    if task:
        await asyncio.to_thread(
            trigger_task_now,
            db_path,
            task_key=task["task_key"],
        )
        return f"已创建记忆生成任务，正在通过平台 Agent 提炼并写入记忆..."
    else:
        return "创建记忆任务失败"


async def _cmd_help(context: dict[str, Any]) -> str:
    lines = ["📋 可用系统指令："]
    lines.append("")
    
    added_keywords = set()
    
    for keyword, cmd in SYSTEM_COMMANDS.items():
        if keyword == "/ok":
            continue
        # 只在遇到主命令，避免重复显示
        cmd_lower = cmd.keyword.lower()
        if cmd_lower in added_keywords:
            continue
        if keyword.lower() != cmd_lower:
            continue
        added_keywords.add(cmd_lower)
        
        lines.append(f"{cmd.keyword}")
        if cmd.aliases:
            alias_str = " | ".join(cmd.aliases)
            lines.append(f"  别名：{alias_str}")
        lines.append(f"  {cmd.description}")
        if cmd.require_bound:
            lines.append("  (仅限绑定者使用)")
        lines.append("")
    
    return "\n".join(lines)


register_command(SystemCommand(
    keyword="/查看指令",
    aliases=("/help", "/指令", "/命令"),
    description="查看所有可用指令",
    handler=_cmd_help,
    require_bound=False,
))


register_command(SystemCommand(
    keyword="/记忆生成",
    aliases=("/memory",),
    description="将文本内容添加到记忆",
    handler=_cmd_memory_create,
    require_bound=False,
))
