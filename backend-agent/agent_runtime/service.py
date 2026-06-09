from __future__ import annotations

"""核心 Agent 服务模块，处理 LLM 调用、流式输出、上下文压缩和输出清洗。"""

import asyncio
import hashlib
import json
import re
from collections import OrderedDict
from contextlib import suppress
from pathlib import Path
from typing import Any, AsyncIterator, Callable, Union
from app.config_loader import Settings

# 导入 asyncio.CancelledError
CancelledError = asyncio.CancelledError
from app.context_store import (
    build_compression_transcript,
    build_context_prompt,
    get_context_compression_disabled_reason,
    get_recent_messages_as_chat_history,
    resolve_context_sender,
    should_compress_context,
    upsert_context_summary,
)
from app.chat_store import get_conversation
from app.utils import default_database_path, extract_error_info, format_error_message
from app.logger import get_logger
from app.db.core import connect_database
from app.db.log_store import insert_project_log
from app.db.memory_usage_audit_store import upsert_memory_usage_audit
from app.db.token_usage_store import record_token_usage
from app.db.ai_work_store import create_ai_work_item, update_ai_work_item
from app.db.slot_store import acquire_chat_compress_lock, release_chat_compress_lock, wait_for_chat_compress_unlock
from app.llm_usage import extract_token_usage, resolve_token_usage
from uuid import uuid4
from agent_runtime.commands import dispatch_system_command, is_command_attempt, is_no_prefix_command, _strip_at_prefix
from agent_runtime.models import build_chat_model
from agent_runtime.prompts import build_system_workflow_prompt
from agent_runtime.tools import RuntimeToolSelection, select_runtime_tools, _current_chat_id, _current_bot_key, _current_project_root, _current_trace_id, _current_call_type
from agent_runtime.skills_integration import notify_owner, read_memory, expand_query_with_llm, _is_query_expansion_enabled
from app.yaml_config import get_yaml_config
from app.chat_store import get_chat_history_by_id, format_chat_history

try:
    import langchain_openai.chat_models.base as _lc_openai_base
    _original_convert_delta = _lc_openai_base._convert_delta_to_message_chunk
    def _patched_convert_delta_to_message_chunk(_dict, default_class):
        result = _original_convert_delta(_dict, default_class)
        rc = _dict.get("reasoning_content")
        if isinstance(rc, str) and rc and hasattr(result, "additional_kwargs"):
            result.additional_kwargs["reasoning_content"] = rc
        return result
    _lc_openai_base._convert_delta_to_message_chunk = _patched_convert_delta_to_message_chunk
except Exception:
    pass

MultimodalContent = Union[str, list[dict[str, Any]]]

_logger = get_logger("agent_runtime.service")
_HIDDEN_REASONING_TAG_NAMES = ("thinking", "reasoning", "analysis", "think")
_HIDDEN_REASONING_BLOCK_PATTERN = re.compile(
    r"<(?P<tag>thinking|reasoning|analysis|think)\b[^>]*>.*?</(?P=tag)>",
    re.IGNORECASE | re.DOTALL,
)
_HIDDEN_REASONING_TAG_PATTERN = re.compile(
    r"</?(?:thinking|reasoning|analysis|think)\b[^>]*>",
    re.IGNORECASE,
)
_HIDDEN_REASONING_OPEN_TAG_RE = re.compile(
    r"<(?P<tag>thinking|reasoning|analysis|think)\b[^>]*>",
    re.IGNORECASE,
)
_HIDDEN_REASONING_CLOSE_TAG_RE = re.compile(
    r"</(?P<tag>thinking|reasoning|analysis|think)\b[^>]*>",
    re.IGNORECASE,
)
_HIDDEN_REASONING_TAG_PAIRS = tuple(
    (f"<{name}>", f"</{name}>")
    for name in sorted(_HIDDEN_REASONING_TAG_NAMES, key=len, reverse=True)
)


def _find_notify_delivery_for_trace(
    database_path: Path | None,
    *,
    trace_id: str,
    bot_key: str,
) -> dict[str, Any] | None:
    if database_path is None or not trace_id or not bot_key:
        return None
    try:
        with connect_database(database_path) as conn:
            row = conn.execute(
                """
                SELECT status, content, metadata_json
                FROM manual_reply_commands
                WHERE bot_key = ?
                  AND metadata_json LIKE ?
                  AND metadata_json LIKE ?
                ORDER BY created_at DESC
                LIMIT 1
                """,
                (
                    bot_key,
                    '%"source": "notify_me_skill"%',
                    f'%"trace_id": "{trace_id}"%',
                ),
            ).fetchone()
    except Exception:
        return None
    if row is None:
        return None
    item = dict(row)
    try:
        item["metadata"] = json.loads(str(item.get("metadata_json") or "{}"))
    except json.JSONDecodeError:
        item["metadata"] = {}
    return item


def _recover_text_from_notify_delivery(delivery: dict[str, Any] | None) -> str:
    if not isinstance(delivery, dict):
        return ""
    content = str(delivery.get("content") or "").strip()
    if not content:
        metadata = delivery.get("metadata") if isinstance(delivery.get("metadata"), dict) else {}
        return str(metadata.get("user_question") or "").strip().strip('"')

    lines = [line.strip() for line in content.splitlines() if line.strip()]
    if len(lines) >= 2 and "任务结果通知" in lines[0]:
        return "\n".join(lines[1:]).strip().strip('"')
    return content.strip('"')
def _cfg(dot_path: str, default: Any = None) -> Any:
    return get_yaml_config().get(dot_path, default)


MEMORY_PACK_USAGE_RULES = """\
使用规则:
- 记忆包只作为历史上下文，当前用户指令优先。
- 不要向用户暴露记忆系统内部机制、文件路径或审计字段。
- 当记忆与当前问题无关或冲突时，说明不确定性，不要强行使用。
- 记忆包可能包含“来源：...”标记；只有最终回答使用了带来源标记的记忆内容，才需要在回答末尾标明对应来源。
- 显式记忆/管理员手工配置内容输出“来源：管理员配置内容”。
- 文档提取内容输出“来源：文档《显示名》”。
- 会话提取、工作笔记、用户画像、时间线等会话沉淀内容不输出面向用户的来源标签。
- 同时使用多类带来源标记的记忆时，来源合并展示，例如“来源：管理员配置内容、文档《核心文档.txt》”。
- 在生成最终回答前必须自检：如果回答依据来自带来源标记的记忆包内容，但末尾没有“来源：...”，必须先补上再输出。
- 来源只作为面向用户的简短出处，不要解释记忆系统、不要输出路径、UUID、trace_id 或审计字段。
- 不要输出原始文件路径、UUID、trace_id、selected_files 或审计字段。
- 如果没有使用记忆包内容，仅依据当前用户输入、常识或工具结果回答，不要添加记忆来源。
"""


def _format_memory_pack_for_prompt(memory_pack: str) -> str:
    text = str(memory_pack or "").strip()
    if not text:
        return ""
    return f"{MEMORY_PACK_USAGE_RULES}\n{text}".strip()


def _render_system_prompt_sections(sections: list[tuple[str, str]], max_chars: int) -> str:
    parts: list[str] = []
    used = 0
    unlimited = int(max_chars or 0) <= 0
    for tag, content in sections:
        if not content.strip():
            continue
        section = f"<{tag}>\n{content.strip()}\n</{tag}>"
        section_len = len(section)
        if not unlimited and used + section_len > max_chars and parts:
            remaining = max_chars - used
            if remaining > 100:
                truncated = content.strip()[:remaining - 20].rstrip() + "\n[已截断]"
                parts.append(f"<{tag}>\n{truncated}\n</{tag}>")
            break
        parts.append(section)
        used += section_len
    return "\n\n".join(parts)


class _HiddenReasoningStreamFilter:
    """流式输出过滤器，过滤模型输出中的推理/思考标签，同时收集推理文本用于日志记录。"""

    def __init__(
        self,
        max_reasoning_chars: int = 10000,
        truncation_notice: str = "[思考链已截断]",
    ) -> None:
        self._buffer = ""
        self._active_tag_name = ""
        self._reasoning_parts: list[str] = []
        self._total_reasoning_chars = 0
        self._max_reasoning_chars = max_reasoning_chars
        self._reasoning_truncated = False
        self._should_stop = False
        self._stop_reason: str = ""
        self._truncation_notice = truncation_notice

    def feed(self, text: str) -> str:
        if not text:
            return ""
        self._buffer += text
        return self._drain(final=False)

    def flush(self) -> str:
        return self._drain(final=True)
    
    def collect_reasoning_text(self, text: str) -> None:
        if not text:
            return
        if self._total_reasoning_chars < self._max_reasoning_chars:
            remaining = self._max_reasoning_chars - self._total_reasoning_chars
            to_append = text[:remaining]
            if len(to_append) < len(text):
                self._reasoning_truncated = True
            self._reasoning_parts.append(to_append)
            self._total_reasoning_chars += len(to_append)
        else:
            self._reasoning_truncated = True
    
    def get_reasoning_text(self) -> str:
        if self._buffer and self._active_tag_name:
            remaining = self._max_reasoning_chars - self._total_reasoning_chars
            if remaining > 0:
                to_append = self._buffer[:remaining]
                if len(to_append) < len(self._buffer):
                    self._reasoning_truncated = True
                self._reasoning_parts.append(to_append)
                self._total_reasoning_chars += len(to_append)
            self._buffer = ""
            self._active_tag_name = ""
        
        reasoning_text = "".join(self._reasoning_parts)
        if self._reasoning_truncated:
            return reasoning_text + self._truncation_notice
        return reasoning_text
    
    @property
    def should_stop(self) -> bool:
        return self._should_stop
    
    @property
    def stop_reason(self) -> str:
        return self._stop_reason

    def _append_reasoning(self, text: str) -> None:
        if not text:
            return
        if self._total_reasoning_chars < self._max_reasoning_chars:
            remaining = self._max_reasoning_chars - self._total_reasoning_chars
            if len(text) > remaining:
                self._reasoning_truncated = True
                text = text[:remaining]
            self._reasoning_parts.append(text)
            self._total_reasoning_chars += len(text)
        else:
            self._reasoning_truncated = True

    def _drain(self, *, final: bool) -> str:
        if not self._buffer:
            return ""

        visible_parts: list[str] = []

        try:
            while self._buffer:
                if self._should_stop:
                    if self._active_tag_name:
                        self._append_reasoning(self._buffer)
                    else:
                        visible_parts.append(self._buffer)
                    self._buffer = ""
                    break
                
                text = self._buffer

                if self._active_tag_name:
                    close_pattern = re.compile(
                        rf"</{self._active_tag_name}\b[^>]*>",
                        re.IGNORECASE,
                    )
                    close_match = close_pattern.search(text)
                    if close_match is None:
                        if (
                            not final
                            and self._total_reasoning_chars + len(text) > self._max_reasoning_chars
                        ):
                            self._append_reasoning(text)
                            self._buffer = ""
                        elif final:
                            self._append_reasoning(text)
                            self._buffer = ""
                        break
                    reasoning_content = text[:close_match.start()]
                    self._append_reasoning(reasoning_content)
                    self._buffer = text[close_match.end():]
                    self._active_tag_name = ""
                    continue

                open_match = _HIDDEN_REASONING_OPEN_TAG_RE.search(text)
                if open_match is not None:
                    visible_parts.append(text[:open_match.start()])
                    self._active_tag_name = open_match.group("tag").lower()
                    self._buffer = text[open_match.end():]
                    continue

                if final:
                    visible_parts.append(text)
                    self._buffer = ""
                    break

                partial_match = _HIDDEN_REASONING_TAG_PATTERN.search(text)
                if partial_match is not None:
                    last_tag_end = partial_match.end()
                    next_partial = _HIDDEN_REASONING_TAG_PATTERN.search(text, last_tag_end)
                    while next_partial is not None:
                        last_tag_end = next_partial.end()
                        next_partial = _HIDDEN_REASONING_TAG_PATTERN.search(text, last_tag_end)
                    visible_parts.append(text[:partial_match.start()])
                    self._buffer = text[partial_match.start():]
                else:
                    partial_lt = text.rfind("<")
                    if partial_lt >= 0:
                        after_lt = text[partial_lt:]
                        if any(after_lt.lower().startswith(f"<{n}") for n in _HIDDEN_REASONING_TAG_NAMES):
                            visible_parts.append(text[:partial_lt])
                            self._buffer = text[partial_lt:]
                        else:
                            visible_parts.append(text)
                            self._buffer = ""
                    else:
                        visible_parts.append(text)
                        self._buffer = ""
                break
        except Exception as e:
            self._should_stop = True
            self._stop_reason = f"思考链处理异常: {type(e).__name__}"
            _logger.warning(f"思考链处理异常: {e}", exc_info=True)

        return "".join(visible_parts)


class AgentService:
    """主服务类，编排 AI Agent 交互，支持流式输出、任务式回答和上下文压缩。"""

    def __init__(self, settings: Settings, project_root: Path | None = None) -> None:
        self.settings = settings
        self.project_root = project_root
        self.database_path = default_database_path(project_root)
        self.logger = get_logger("agent_runtime.service")
        self._agent_cache: OrderedDict[str, Any] = OrderedDict()
        self._tools_hash: str = ""

    def invalidate_cache(self) -> None:
        self._agent_cache.clear()
        self._tools_hash = ""

    @staticmethod
    def _should_audit_memory_usage(call_type: str) -> bool:
        return call_type in {"chat", "draft"}

    def _write_memory_usage_audit(
        self,
        *,
        trace_id: str,
        chat_id: str,
        bot_key: str,
        call_type: str,
        user_query: str,
        memory_result: dict[str, Any] | None,
        status: str,
        final_answer: str | None = None,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> None:
        if not trace_id or not self._should_audit_memory_usage(call_type):
            return
        payload = memory_result or {}
        try:
            upsert_memory_usage_audit(
                self.database_path,
                trace_id=trace_id,
                chat_id=chat_id,
                bot_key=bot_key,
                call_type=call_type,
                status=status,
                user_query=user_query,
                memory_pack=str(payload.get("memory_pack", "") or ""),
                selected_files=[str(item) for item in payload.get("selected_files", [])],
                selected_sections=[str(item) for item in payload.get("selected_sections", [])],
                omitted_files=[str(item) for item in payload.get("omitted_files", [])],
                token_budget_used_estimate=max(0, int(payload.get("token_budget_used_estimate", 0) or 0)),
                confidence=str(payload.get("confidence", "") or ""),
                needs_more_memory=bool(payload.get("needs_more_memory", False)),
                reason=str(payload.get("reason", "") or ""),
                final_answer=final_answer,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
                total_tokens=(
                    max(0, int(input_tokens or 0))
                    + max(0, int(output_tokens or 0))
                    if input_tokens is not None or output_tokens is not None
                    else None
                ),
            )
        except Exception:
            self.logger.warning(
                "Failed to persist memory usage audit",
                exc_info=True,
                extra={"trace_id": trace_id, "category": "ai"} if trace_id else {"category": "ai"},
            )

    @staticmethod
    def _context_compression_skip_response(skip_reason: str, message: str) -> dict[str, Any]:
        return {
            "triggered": False,
            "skipped": True,
            "compressed": False,
            "summary": "",
            "error": "",
            "skip_reason": skip_reason,
            "message": message,
        }

    async def answer(
        self,
        user_input: MultimodalContent,
        *,
        chat_id: str | None = None,
        sender_id: str = "",
        sender_name: str = "",
        trace_id: str = "",
        cancel_check: Callable[[], bool] | None = None,
        call_type: str = "answer",
        bot_key: str = "",
    ) -> str:
        if not self.settings.agent.enabled:
            self._log_agent_fallback(
                trace_id=trace_id,
                call_type=call_type,
                chat_id=chat_id or "",
                reason="Agent 未启用，返回降级回复",
            )
            return self.settings.agent.fallback_text

        if isinstance(user_input, str) and is_command_attempt(user_input):
            return await dispatch_system_command(
                _strip_at_prefix(user_input).lower(),
                context={
                    "chat_id": chat_id or "",
                    "bot_key": bot_key,
                    "original_text": user_input,
                    "database_path": self.database_path,
                },
            )

        if isinstance(user_input, str) and is_no_prefix_command(user_input):
            return await dispatch_system_command(
                _strip_at_prefix(user_input).lower(),
                context={
                    "chat_id": chat_id or "",
                    "bot_key": bot_key,
                    "original_text": user_input,
                    "database_path": self.database_path,
                },
            )

        user_query = _selection_text_from_user_input(user_input)
        audit_trace_id = trace_id or uuid4().hex
        memory_result: dict[str, Any] | None = None
        try:
            chat_id_token = _current_chat_id.set(chat_id or "")
            bot_key_token = _current_bot_key.set(bot_key)
            project_root_token = _current_project_root.set(str(self.project_root) if self.project_root else "")
            trace_id_token = _current_trace_id.set(trace_id)
            call_type_token = _current_call_type.set(call_type)
            try:
                context_prompt = ""
                chat_history: list[dict[str, Any]] = []
                if chat_id:
                    context_sender = resolve_context_sender(
                        database_path=self.database_path,
                        chat_id=chat_id,
                        sender_id=sender_id,
                        sender_name=sender_name,
                    )
                    context_prompt = build_context_prompt(
                        database_path=self.database_path,
                        chat_id=chat_id,
                        sender_id=context_sender["sender_id"],
                        sender_name=context_sender["sender_name"],
                        settings=self.settings,
                    )
                    chat_history = get_recent_messages_as_chat_history(
                        database_path=self.database_path,
                        chat_id=chat_id,
                        sender_id=context_sender["sender_id"],
                        sender_name=context_sender["sender_name"],
                        settings=self.settings,
                        exclude_trace_id=trace_id,
                    )
                expanded_terms = await self._expand_query_terms(user_query, trace_id=trace_id)
                selection = await self._select_runtime_tools(user_input, expanded_terms=expanded_terms)
                system_prompt, memory_result = await self._build_system_prompt(
                    context_prompt,
                    selection,
                    user_query,
                    trace_id=trace_id,
                    expanded_terms=expanded_terms,
                )
                self._write_memory_usage_audit(
                    trace_id=audit_trace_id,
                    chat_id=chat_id or "",
                    bot_key=bot_key,
                    call_type=call_type,
                    user_query=user_query,
                    memory_result=memory_result,
                    status="started",
                )
                self._log_agent_prompt(
                    trace_id=trace_id,
                    call_type=call_type,
                    chat_id=chat_id or "",
                    user_input=user_input,
                    context_prompt=context_prompt,
                    chat_history=chat_history,
                    system_prompt=system_prompt,
                    selection=selection,
                )
                agent = await self._get_agent(system_prompt, selection)
                task = asyncio.create_task(
                    agent.ainvoke(_build_agent_input(user_input, chat_history))
                )
                result = await _wait_with_cancel(
                    task,
                    timeout=self.settings.agent.timeout_seconds,
                    cancel_check=cancel_check,
                )
                tokens = _record_tokens_from_result(
                    result,
                    database_path=self.database_path,
                    settings=self.settings,
                    call_type=call_type,
                    chat_id=chat_id or "",
                    bot_key=bot_key,
                    trace_id=trace_id,
                    prompt_text="\n".join(
                        part
                        for part in (
                            system_prompt,
                            _format_chat_history_for_log(chat_history),
                            _stringify_user_input(user_input),
                        )
                        if part
                    ),
                )
                answer = _extract_text(result) or self.settings.agent.fallback_text
                sanitized = sanitize_agent_output(answer, self.settings.agent.fallback_text)
                if sanitized == self.settings.agent.fallback_text:
                    reason = "模型未返回有效内容" if not answer else "模型输出被安全过滤或为空"
                    self._log_agent_fallback(
                        trace_id=trace_id,
                        call_type=call_type,
                        chat_id=chat_id or "",
                        reason=reason,
                    )
                self._write_memory_usage_audit(
                    trace_id=audit_trace_id,
                    chat_id=chat_id or "",
                    bot_key=bot_key,
                    call_type=call_type,
                    user_query=user_query,
                    memory_result=memory_result,
                    status="success",
                    final_answer=sanitized,
                    input_tokens=tokens.get("input_tokens", 0),
                    output_tokens=tokens.get("output_tokens", 0),
                )
                self._log_agent_answer(
                    trace_id=trace_id,
                    call_type=call_type,
                    chat_id=chat_id or "",
                    answer=sanitized,
                    input_tokens=tokens.get("input_tokens", 0),
                    output_tokens=tokens.get("output_tokens", 0),
                )
                return sanitized or self.settings.agent.fallback_text
            finally:
                _current_chat_id.reset(chat_id_token)
                _current_bot_key.reset(bot_key_token)
                _current_project_root.reset(project_root_token)
                _current_trace_id.reset(trace_id_token)
                _current_call_type.reset(call_type_token)
        except asyncio.CancelledError:
            self._log_agent_fallback(
                trace_id=trace_id,
                call_type=call_type,
                chat_id=chat_id or "",
                reason="Agent 任务被取消，返回降级回复",
            )
            self._write_memory_usage_audit(
                trace_id=audit_trace_id,
                chat_id=chat_id or "",
                bot_key=bot_key,
                call_type=call_type,
                user_query=user_query,
                memory_result=memory_result,
                status="cancelled",
                final_answer=self.settings.agent.fallback_text,
            )
            return self.settings.agent.fallback_text
        except Exception:
            log_kwargs = {"extra": {"trace_id": trace_id, "category": "ai"}} if trace_id else {"extra": {"category": "ai"}}
            self.logger.exception("Agent 工作流执行失败。", **log_kwargs)
            self._write_memory_usage_audit(
                trace_id=audit_trace_id,
                chat_id=chat_id or "",
                bot_key=bot_key,
                call_type=call_type,
                user_query=user_query,
                memory_result=memory_result,
                status="failed",
                final_answer=self.settings.agent.fallback_text,
            )
            self._log_agent_fallback(
                trace_id=trace_id,
                call_type=call_type,
                chat_id=chat_id or "",
                reason="Agent 工作流异常，返回降级回复",
            )
            return self.settings.agent.fallback_text

    async def answer_for_task(
        self,
        user_input: str,
        *,
        task_key: str = "",
        trace_id: str = "",
        force_skill_names: list[str] | None = None,
        force_mcp_server_ids: list[str] | None = None,
        bot_key: str = "",
    ) -> tuple[str, int, int]:
        """专门为 bot_task 设计的回答方法，支持强制指定 Skill 和 MCP，不依赖 chat_id，最后自动调用 notify-me 通知结果"""
        if not self.settings.agent.enabled:
            self._log_agent_fallback(
                trace_id=trace_id,
                call_type="bot_task",
                chat_id="",
                reason="Agent 未启用，返回降级回复",
            )
            return self.settings.agent.fallback_text, 0, 0

        audit_trace_id = trace_id or uuid4().hex
        memory_result: dict[str, Any] | None = None
        
        # 获取 bot 绑定的管理员会话 chat_id
        owner_chat_id = ""
        database_path = default_database_path()
        try:
            with connect_database(database_path) as conn:
                row = conn.execute(
                    """
                    SELECT chat_id, external_chat_id
                    FROM conversations
                    WHERE conversation_kind = 'me'
                      AND bot_key = ?
                    ORDER BY updated_at DESC
                    LIMIT 1
                    """,
                    (bot_key,),
                ).fetchone()
            if row:
                owner_chat_id = str(row["external_chat_id"] or row["chat_id"] or "").strip()
        except Exception as e:
            _logger.warning(f"Failed to find owner conversation for bot_key={bot_key}: {e}")
        
        try:
            bot_key_token = _current_bot_key.set(bot_key)
            project_root_token = _current_project_root.set(str(self.project_root) if self.project_root else "")
            trace_id_token = _current_trace_id.set(trace_id)
            chat_id_token = _current_chat_id.set(owner_chat_id)
            call_type_token = _current_call_type.set("bot_task")
            try:
                context_prompt = ""
                chat_history: list[dict[str, Any]] = []
                # 直接使用 select_runtime_tools_for_task
                from agent_runtime.tools import select_runtime_tools_for_task
                selection = await select_runtime_tools_for_task(
                    self.settings,
                    project_root=self.project_root,
                    user_input_text=user_input,
                    force_skill_names=force_skill_names,
                    force_mcp_server_ids=force_mcp_server_ids,
                )

                # 单独构建 bot_task 专属提示词
                # 1. 获取底层工作流规则
                from agent_runtime.prompts import build_system_workflow_prompt
                workflow_prompt = build_system_workflow_prompt(project_root=self.project_root)

                # 2. 获取记忆包
                memory_result = {
                    "memory_pack": "",
                    "selected_files": [],
                    "selected_sections": [],
                    "omitted_files": [],
                    "token_budget_used_estimate": 0,
                    "confidence": "",
                    "needs_more_memory": False,
                    "reason": "",
                }
                try:
                    memory_result = await read_memory(
                        user_input,
                        project_root=self.project_root,
                        settings=self.settings,
                        database_path=self.database_path,
                        trace_id=trace_id,
                    )
                except Exception as e:
                    _logger.warning(f"Failed to read memory, skipping: {e}")

                memory_pack = _format_memory_pack_for_prompt(memory_result.get("memory_pack", ""))

                tool_instruction_parts: list[str] = [
                    "任务完成条件：得到实际结果后、最终输出前，必须调用 `notify-me` 发送结果通知；不得以用户没有要求通知、问题很简单、已直接回答为理由跳过。调用时必须传入 `--content` 参数，参数值必须是任务完成后的实际结果内容，禁止传入 None、none、空字符串或占位文本。"
                ]
                if selection.prompt_instructions:
                    tool_instruction_parts.extend(
                        inst for inst in selection.prompt_instructions if inst and inst.strip()
                    )
                tool_instructions = "\n".join(tool_instruction_parts)

                skill_context = str(selection.skill_context or "").strip()
                system_prompt = _render_system_prompt_sections(
                    [
                        ("底层工作流规则", workflow_prompt),
                        ("记忆包", memory_pack),
                        ("本轮执行约束", tool_instructions),
                        ("Skill 指令", skill_context),
                    ],
                    0,
                )

                self._write_memory_usage_audit(
                    trace_id=audit_trace_id,
                    chat_id="",
                    bot_key=bot_key,
                    call_type="bot_task",
                    user_query=user_input,
                    memory_result=memory_result,
                    status="started",
                )
                self._log_agent_prompt(
                    trace_id=trace_id,
                    call_type="bot_task",
                    chat_id="",
                    user_input=user_input,
                    context_prompt=context_prompt,
                    chat_history=chat_history,
                    system_prompt=system_prompt,
                    selection=selection,
                )
                agent = await self._get_agent(system_prompt, selection, no_retry=True)
                task = asyncio.create_task(
                    self._invoke_agent_with_event_logs(
                        agent=agent,
                        agent_input=_build_agent_input(user_input, chat_history),
                        trace_id=trace_id,
                        call_type="bot_task",
                        chat_id="",
                        bot_key=bot_key,
                        cancel_check=None,
                        no_output_limit=True,
                    )
                )
                sanitized, input_tokens, output_tokens = await task
                if sanitized == self.settings.agent.fallback_text:
                    reason = "模型未返回有效内容或输出被安全过滤"
                    self._log_agent_fallback(
                        trace_id=trace_id,
                        call_type="bot_task",
                        chat_id="",
                        reason=reason,
                    )
                self._write_memory_usage_audit(
                    trace_id=audit_trace_id,
                    chat_id="",
                    bot_key=bot_key,
                    call_type="bot_task",
                    user_query=user_input,
                    memory_result=memory_result,
                    status="completed",
                    final_answer=sanitized,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                self._log_agent_answer(
                    trace_id=trace_id,
                    call_type="bot_task",
                    chat_id="",
                    answer=sanitized,
                    input_tokens=input_tokens,
                    output_tokens=output_tokens,
                )
                return sanitized or self.settings.agent.fallback_text, input_tokens, output_tokens
            finally:
                _current_bot_key.reset(bot_key_token)
                _current_project_root.reset(project_root_token)
                _current_trace_id.reset(trace_id_token)
                _current_chat_id.reset(chat_id_token)
                _current_call_type.reset(call_type_token)
        except CancelledError:
            # 确保 memory_result 有默认值
            safe_memory_result = memory_result or {}
            self._write_memory_usage_audit(
                trace_id=audit_trace_id,
                chat_id="",
                bot_key=bot_key,
                call_type="bot_task",
                user_query=user_input,
                memory_result=safe_memory_result,
                status="cancelled",
                final_answer=self.settings.agent.fallback_text,
            )
            return self.settings.agent.fallback_text, 0, 0
        except Exception:
            # 确保 memory_result 有默认值
            safe_memory_result = memory_result or {}
            recovered_delivery = _find_notify_delivery_for_trace(
                self.database_path,
                trace_id=trace_id,
                bot_key=bot_key,
            )
            if recovered_delivery is not None:
                recovered_text = _recover_text_from_notify_delivery(recovered_delivery) or "已通过 notify-me 发送结果"
                self._write_memory_usage_audit(
                    trace_id=audit_trace_id,
                    chat_id="",
                    bot_key=bot_key,
                    call_type="bot_task",
                    user_query=user_input,
                    memory_result=safe_memory_result,
                    status="completed",
                    final_answer=recovered_text,
                )
                insert_project_log(
                    self.database_path,
                    trace_id=trace_id,
                    level="WARNING",
                    category="ai",
                    source="agent_runtime.service",
                    message="Agent 任务工作流在 notify-me 成功后异常，已按成功收口",
                    detail=(
                        f"notify_status={recovered_delivery.get('status', '')}\n"
                        f"recovered_answer={recovered_text[:1000]}"
                    ),
                )
                self._log_agent_answer(
                    trace_id=trace_id,
                    call_type="bot_task",
                    chat_id="",
                    answer=recovered_text,
                )
                return recovered_text, 0, 0
            log_kwargs = {"extra": {"trace_id": trace_id, "category": "ai"}} if trace_id else {"extra": {"category": "ai"}}
            self.logger.exception("Agent 任务工作流执行失败。", **log_kwargs)
            self._log_agent_fallback(
                trace_id=trace_id,
                call_type="bot_task",
                chat_id="",
                reason="Agent 工作流异常，返回降级回复",
            )
            return self.settings.agent.fallback_text, 0, 0

    async def stream_answer(
        self,
        user_input: MultimodalContent,
        *,
        chat_id: str | None = None,
        sender_id: str = "",
        sender_name: str = "",
        trace_id: str = "",
        cancel_check: Callable[[], bool] | None = None,
        call_type: str = "answer",
        bot_key: str = "",
    ) -> AsyncIterator[str]:
        if not self.settings.agent.enabled:
            self._log_agent_fallback(
                trace_id=trace_id,
                call_type=call_type,
                chat_id=chat_id or "",
                reason="Agent 未启用，返回降级回复",
            )
            yield self.settings.agent.fallback_text
            return

        if isinstance(user_input, str) and is_command_attempt(user_input):
            result = await dispatch_system_command(
                _strip_at_prefix(user_input).lower(),
                context={
                    "chat_id": chat_id or "",
                    "bot_key": bot_key,
                    "original_text": user_input,
                    "database_path": self.database_path,
                },
            )
            self._log_agent_answer(
                trace_id=trace_id,
                call_type=call_type,
                chat_id=chat_id or "",
                answer=result,
            )
            yield result
            return

        if isinstance(user_input, str) and is_no_prefix_command(user_input):
            result = await dispatch_system_command(
                _strip_at_prefix(user_input).lower(),
                context={
                    "chat_id": chat_id or "",
                    "bot_key": bot_key,
                    "original_text": user_input,
                    "database_path": self.database_path,
                },
            )
            self._log_agent_answer(
                trace_id=trace_id,
                call_type=call_type,
                chat_id=chat_id or "",
                answer=result,
            )
            yield result
            return

        context_prompt = ""
        stream_chat_history: list[dict[str, Any]] = []
        context_sender = {"sender_id": "", "sender_name": ""}
        if chat_id:
            context_sender = resolve_context_sender(
                database_path=self.database_path,
                chat_id=chat_id,
                sender_id=sender_id,
                sender_name=sender_name,
            )
            context_prompt = build_context_prompt(
                database_path=self.database_path,
                chat_id=chat_id,
                sender_id=context_sender["sender_id"],
                sender_name=context_sender["sender_name"],
                settings=self.settings,
            )
            stream_chat_history = get_recent_messages_as_chat_history(
                database_path=self.database_path,
                chat_id=chat_id,
                sender_id=context_sender["sender_id"],
                sender_name=context_sender["sender_name"],
                settings=self.settings,
                exclude_trace_id=trace_id,
            )

        if cancel_check and cancel_check():
            return

        user_query = _selection_text_from_user_input(user_input)
        audit_trace_id = trace_id or uuid4().hex
        memory_result: dict[str, Any] | None = None
        audit_status = ""
        audit_final_answer = ""
        chat_id_token = _current_chat_id.set(chat_id or "")
        bot_key_token = _current_bot_key.set(bot_key)
        project_root_token = _current_project_root.set(str(self.project_root) if self.project_root else "")
        trace_id_token = _current_trace_id.set(trace_id)
        call_type_token = _current_call_type.set(call_type)

        try:
            expanded_terms = await self._expand_query_terms(user_query, trace_id=trace_id)
            selection = await self._select_runtime_tools(user_input, expanded_terms=expanded_terms)
        except Exception:
            log_kwargs = {"extra": {"trace_id": trace_id, "category": "ai"}} if trace_id else {"extra": {"category": "ai"}}
            self.logger.exception("Agent 工具选择失败。", **log_kwargs)
            self._write_memory_usage_audit(
                trace_id=audit_trace_id,
                chat_id=chat_id or "",
                bot_key=bot_key,
                call_type=call_type,
                user_query=user_query,
                memory_result=memory_result,
                status="failed",
                final_answer=self.settings.agent.fallback_text,
            )
            self._log_agent_fallback(
                trace_id=trace_id,
                call_type=call_type,
                chat_id=chat_id or "",
                reason="Agent 工具选择失败，返回降级回复",
            )
            _current_chat_id.reset(chat_id_token)
            _current_bot_key.reset(bot_key_token)
            _current_project_root.reset(project_root_token)
            _current_trace_id.reset(trace_id_token)
            _current_call_type.reset(call_type_token)
            yield self.settings.agent.fallback_text
            return

        if cancel_check and cancel_check():
            self._write_memory_usage_audit(
                trace_id=audit_trace_id,
                chat_id=chat_id or "",
                bot_key=bot_key,
                call_type=call_type,
                user_query=user_query,
                memory_result=memory_result,
                status="cancelled",
            )
            _current_chat_id.reset(chat_id_token)
            _current_bot_key.reset(bot_key_token)
            _current_project_root.reset(project_root_token)
            _current_trace_id.reset(trace_id_token)
            _current_call_type.reset(call_type_token)
            return

        try:
            system_prompt, memory_result = await self._build_system_prompt(
                context_prompt,
                selection,
                user_query,
                trace_id=trace_id,
                expanded_terms=expanded_terms,
            )
        except Exception:
            log_kwargs = {"extra": {"trace_id": trace_id, "category": "ai"}} if trace_id else {"extra": {"category": "ai"}}
            self.logger.exception("Agent 系统提示词构建失败。", **log_kwargs)
            self._write_memory_usage_audit(
                trace_id=audit_trace_id,
                chat_id=chat_id or "",
                bot_key=bot_key,
                call_type=call_type,
                user_query=user_query,
                memory_result=memory_result,
                status="failed",
                final_answer=self.settings.agent.fallback_text,
            )
            self._log_agent_fallback(
                trace_id=trace_id,
                call_type=call_type,
                chat_id=chat_id or "",
                reason="Agent 系统提示词构建失败，返回降级回复",
            )
            _current_chat_id.reset(chat_id_token)
            _current_bot_key.reset(bot_key_token)
            _current_project_root.reset(project_root_token)
            _current_trace_id.reset(trace_id_token)
            _current_call_type.reset(call_type_token)
            yield self.settings.agent.fallback_text
            return
        self._write_memory_usage_audit(
            trace_id=audit_trace_id,
            chat_id=chat_id or "",
            bot_key=bot_key,
            call_type=call_type,
            user_query=user_query,
            memory_result=memory_result,
            status="started",
        )
        audit_status = "started"
        self._log_agent_prompt(
            trace_id=trace_id,
            call_type=call_type,
            chat_id=chat_id or "",
            user_input=user_input,
            context_prompt=context_prompt,
            chat_history=stream_chat_history,
            system_prompt=system_prompt,
            selection=selection,
        )
        usage_prompt = "\n".join(
            part
            for part in (
                system_prompt,
                _format_chat_history_for_log(stream_chat_history),
                _stringify_user_input(user_input),
            )
            if part
        )
        try:
            agent = await self._get_agent(system_prompt, selection)
        except Exception:
            log_kwargs = {"extra": {"trace_id": trace_id, "category": "ai"}} if trace_id else {"extra": {"category": "ai"}}
            self.logger.exception("Agent 构建失败。", **log_kwargs)
            self._write_memory_usage_audit(
                trace_id=audit_trace_id,
                chat_id=chat_id or "",
                bot_key=bot_key,
                call_type=call_type,
                user_query=user_query,
                memory_result=memory_result,
                status="failed",
                final_answer=self.settings.agent.fallback_text,
            )
            self._log_agent_fallback(
                trace_id=trace_id,
                call_type=call_type,
                chat_id=chat_id or "",
                reason="Agent 构建失败，返回降级回复",
            )
            _current_chat_id.reset(chat_id_token)
            _current_bot_key.reset(bot_key_token)
            _current_project_root.reset(project_root_token)
            _current_trace_id.reset(trace_id_token)
            _current_call_type.reset(call_type_token)
            yield self.settings.agent.fallback_text
            return

        if cancel_check and cancel_check():
            self._write_memory_usage_audit(
                trace_id=audit_trace_id,
                chat_id=chat_id or "",
                bot_key=bot_key,
                call_type=call_type,
                user_query=user_query,
                memory_result=memory_result,
                status="cancelled",
            )
            _current_chat_id.reset(chat_id_token)
            _current_bot_key.reset(bot_key_token)
            _current_project_root.reset(project_root_token)
            _current_trace_id.reset(trace_id_token)
            _current_call_type.reset(call_type_token)
            return
        collected_tokens: list[str] = []
        total_chunks = 0
        final_result: Any = None
        recorded_model_outputs: set[int] = set()
        accumulated_input_tokens: int = 0
        accumulated_output_tokens: int = 0
        last_recorded_output: Any = None
        _stream_content_received = False
        sentinel = object()
        producer_task: asyncio.Task[Any] | None = None
        output_filter = _HiddenReasoningStreamFilter(
            max_reasoning_chars=self.settings.agent.max_reasoning_chars,
            truncation_notice=self.settings.agent.reasoning_truncation_notice,
        )

        async def _produce_events(event_queue: asyncio.Queue[Any]) -> None:
            stream_gen = agent.astream_events(
                _build_agent_input(user_input, stream_chat_history),
                version="v2",
            )
            try:
                async for event in stream_gen:
                    if cancel_check and cancel_check():
                        break
                    await event_queue.put(event)
            except asyncio.CancelledError:
                pass
            except BaseException as exc:
                await event_queue.put(exc)
            finally:
                if hasattr(stream_gen, "aclose"):
                    await stream_gen.aclose()
                await event_queue.put(sentinel)

        try:
            event_queue: asyncio.Queue[Any] = asyncio.Queue()
            producer_task = asyncio.create_task(_produce_events(event_queue))
            while True:
                if cancel_check and cancel_check():
                    producer_task.cancel()
                    with suppress(asyncio.CancelledError):
                        await producer_task
                    return
                try:
                    queued = await asyncio.wait_for(event_queue.get(), timeout=0.5)
                except asyncio.TimeoutError:
                    continue
                if queued is sentinel:
                    break
                if isinstance(queued, BaseException):
                    raise queued
                event = queued

                kind = event.get("event", "")
                name = event.get("name", "")

                if kind in ("on_chat_model_stream", "on_llm_new_token", "on_token"):
                    chunk = event.get("data", {}).get("chunk")
                    if chunk is None:
                        data = event.get("data", {})
                        token = data.get("token") or data.get("text") or data.get("content")
                        if isinstance(token, str) and token:
                            visible_text = output_filter.feed(token)
                            if visible_text:
                                _stream_content_received = True
                                total_chunks += 1
                                max_chunks = self.settings.agent.max_stream_chunks
                                if total_chunks > max_chunks:
                                    self.logger.warning(
                                        "Agent 流式输出超过 %d 字符，强制截断。",
                                        max_chunks,
                                        extra={"trace_id": trace_id, "category": "ai"} if trace_id else {"category": "ai"},
                                    )
                                    yield self.settings.agent.truncation_notice
                                    break
                                collected_tokens.append(visible_text)
                                yield visible_text
                        continue
                    
                    # 调试日志：记录 chunk 结构（仅前几个 chunk）
                    if total_chunks < 5 and isinstance(chunk, dict):
                        self.logger.debug(
                            "chunk[dict] keys=%s reasoning_content=%s content_preview=%s",
                            list(chunk.keys()),
                            chunk.get("reasoning_content"),
                            str(chunk.get("content", ""))[:100],
                            extra={"trace_id": trace_id, "category": "ai"} if trace_id else {"category": "ai"},
                        )
                    elif total_chunks < 5:
                        msg_obj = getattr(chunk, "message", None)
                        if msg_obj is not None:
                            content_preview = str(getattr(msg_obj, "content", ""))[:100]
                            self.logger.debug(
                                "chunk[obj] type=%s msg_type=%s has_reasoning=%s additional_kwargs_keys=%s content_preview=%s",
                                type(chunk).__name__,
                                type(msg_obj).__name__,
                                hasattr(msg_obj, "reasoning_content"),
                                list(getattr(msg_obj, "additional_kwargs", {}).keys()),
                                content_preview,
                                extra={"trace_id": trace_id, "category": "ai"} if trace_id else {"category": "ai"},
                            )
                    
                    # 处理 chunk 对象
                    content = getattr(chunk, "content", None)
                    if content is None and isinstance(chunk, dict):
                        content = chunk.get("content") or chunk.get("text")
                    
                    # 处理 reasoning_content 字段
                    # LangChain ChatOpenAI 不提取 reasoning_content，需要从多个位置获取
                    reasoning_content = getattr(chunk, "reasoning_content", None)
                    if reasoning_content is None and isinstance(chunk, dict):
                        reasoning_content = chunk.get("reasoning_content")
                    if reasoning_content is None:
                        msg_obj = getattr(chunk, "message", None) if not isinstance(chunk, dict) else None
                        if msg_obj is not None:
                            reasoning_content = getattr(msg_obj, "reasoning_content", None)
                            if reasoning_content is None:
                                ak = getattr(msg_obj, "additional_kwargs", None)
                                if isinstance(ak, dict):
                                    reasoning_content = ak.get("reasoning_content") or ak.get("reasoning")
                    if reasoning_content is None and isinstance(chunk, dict):
                        ak = chunk.get("additional_kwargs")
                        if isinstance(ak, dict):
                            reasoning_content = ak.get("reasoning_content") or ak.get("reasoning")
                    if isinstance(reasoning_content, str) and reasoning_content:
                        output_filter.collect_reasoning_text(reasoning_content)
                    
                    if isinstance(content, str) and content:
                        visible_text = output_filter.feed(content)
                        if visible_text:
                            _stream_content_received = True
                            total_chunks += 1
                            max_chunks = self.settings.agent.max_stream_chunks
                            if total_chunks > max_chunks:
                                self.logger.warning(
                                    "Agent 流式输出超过 %d 字符，强制截断。",
                                    max_chunks,
                                    extra={"trace_id": trace_id, "category": "ai"} if trace_id else {"category": "ai"},
                                )
                                yield self.settings.agent.truncation_notice
                                break
                            collected_tokens.append(visible_text)
                            yield visible_text
                    elif isinstance(content, list):
                        for item in content:
                            text = ""
                            is_reasoning = False
                            if isinstance(item, dict):
                                item_type = str(item.get("type", "")).strip().lower()
                                text = item.get("text", "") or item.get("content", "")
                                if item_type in ("reasoning", "thinking", "thought"):
                                    is_reasoning = True
                            elif isinstance(item, str):
                                text = item
                            if is_reasoning and text:
                                output_filter.collect_reasoning_text(text)
                                continue
                            visible_text = output_filter.feed(text)
                            if not visible_text:
                                continue
                            _stream_content_received = True
                            total_chunks += 1
                            max_chunks = self.settings.agent.max_stream_chunks
                            if total_chunks > max_chunks:
                                self.logger.warning(
                                    "Agent 流式输出超过 %d 字符，强制截断。",
                                    max_chunks,
                                    extra={"trace_id": trace_id, "category": "ai"} if trace_id else {"category": "ai"},
                                )
                                yield self.settings.agent.truncation_notice
                                break
                            collected_tokens.append(visible_text)
                            yield visible_text
                        else:
                            continue
                        break

                elif kind == "on_chat_model_end":
                    output = event.get("data", {}).get("output")
                    if output is not None:
                        last_recorded_output = output
                        recorded_model_outputs.add(id(output))
                        evt_tokens = _record_tokens_from_response(
                            output,
                            database_path=self.database_path,
                            settings=self.settings,
                            call_type=call_type,
                            chat_id=chat_id or "",
                            bot_key=bot_key,
                            trace_id=trace_id,
                            prompt_text=usage_prompt,
                        )
                        accumulated_input_tokens += evt_tokens.get("input_tokens", 0)
                        accumulated_output_tokens += evt_tokens.get("output_tokens", 0)
                        _extract_and_collect_reasoning(output, output_filter)
                        if not _stream_content_received:
                            content = getattr(output, "content", None)
                            if content is None and isinstance(output, dict):
                                content = output.get("content")
                            has_tool_calls = bool(
                                getattr(output, "tool_calls", None)
                                or getattr(output, "additional_kwargs", {}).get("tool_calls")
                            )
                            if isinstance(content, list) and not has_tool_calls:
                                for item in content:
                                    text = ""
                                    is_reasoning = False
                                    if isinstance(item, dict):
                                        item_type = str(item.get("type", "")).strip().lower()
                                        text = item.get("text", "") or item.get("content", "")
                                        if item_type in ("reasoning", "thinking", "thought"):
                                            is_reasoning = True
                                    elif isinstance(item, str):
                                        text = item
                                    if is_reasoning:
                                        if isinstance(text, str) and text:
                                            output_filter.collect_reasoning_text(text)
                                        continue
                                    if not text:
                                        continue
                                    visible_text = output_filter.feed(text)
                                    if visible_text and visible_text.strip():
                                        total_chunks += 1
                                        collected_tokens.append(visible_text)
                                        yield visible_text
                        _stream_content_received = False
                elif kind == "on_chain_stream":
                    chunk = event.get("data", {}).get("chunk")
                    if chunk is None:
                        chunk = event.get("data", {}).get("output")
                    if chunk is not None and name != "model":
                        if isinstance(chunk, dict) and "messages" in chunk:
                            final_result = chunk
                            last_recorded_output = chunk
                            _extract_and_collect_reasoning(chunk, output_filter)
                        elif name == "LangGraph":
                            final_result = chunk
                            last_recorded_output = chunk
                            _extract_and_collect_reasoning(chunk, output_filter)

                elif kind == "on_chain_end":
                    output = event.get("data", {}).get("output")
                    if name == "model" and isinstance(output, list) and output and id(output[-1]) not in recorded_model_outputs:
                        last_recorded_output = output[-1]
                        evt_tokens = _record_tokens_from_result(
                            {"messages": output},
                            database_path=self.database_path,
                            settings=self.settings,
                            call_type=call_type,
                            chat_id=chat_id or "",
                            bot_key=bot_key,
                            trace_id=trace_id,
                            prompt_text=usage_prompt,
                        )
                        accumulated_input_tokens += evt_tokens.get("input_tokens", 0)
                        accumulated_output_tokens += evt_tokens.get("output_tokens", 0)
                    if output is not None and name != "model":
                        if isinstance(output, dict) and "messages" in output:
                            final_result = output
                            _extract_and_collect_reasoning(output, output_filter)
                        elif name == "LangGraph":
                            final_result = output
                            _extract_and_collect_reasoning(output, output_filter)

                elif kind == "on_tool_start":
                    tool_name = event.get("name", "unknown")
                    self._log_agent_tool_event(
                        trace_id=trace_id,
                        phase="start",
                        tool_name=str(tool_name),
                        payload=event.get("data", {}).get("input"),
                    )

                elif kind == "on_tool_end":
                    tool_output = event.get("data", {}).get("output", "")
                    self._log_agent_tool_event(
                        trace_id=trace_id,
                        phase="end",
                        tool_name=str(event.get("name", "unknown")),
                        payload=tool_output,
                    )

            trailing_visible_text = output_filter.flush()
            if trailing_visible_text:
                collected_tokens.append(trailing_visible_text)

            if cancel_check and cancel_check():
                return

            if accumulated_input_tokens == 0 and accumulated_output_tokens == 0:
                if final_result is not None:
                    final_tokens = _record_tokens_from_result(
                        final_result,
                        database_path=self.database_path,
                        settings=self.settings,
                        call_type=call_type,
                        chat_id=chat_id or "",
                        bot_key=bot_key,
                        trace_id=trace_id,
                        prompt_text=usage_prompt,
                    )
                    accumulated_input_tokens = final_tokens.get("input_tokens", 0)
                    accumulated_output_tokens = final_tokens.get("output_tokens", 0)
                elif last_recorded_output is not None:
                    final_tokens = _record_tokens_from_response(
                        last_recorded_output,
                        database_path=self.database_path,
                        settings=self.settings,
                        call_type=call_type,
                        chat_id=chat_id or "",
                        bot_key=bot_key,
                        trace_id=trace_id,
                        prompt_text=usage_prompt,
                    )
                    accumulated_input_tokens = final_tokens.get("input_tokens", 0)
                    accumulated_output_tokens = final_tokens.get("output_tokens", 0)

            full_text = "".join(collected_tokens)
            
            if not full_text.strip():
                fallback_text = ""
                if final_result is not None:
                    fallback_text = _extract_text(final_result)
                if not fallback_text and last_recorded_output is not None:
                    fallback_text = _extract_message_content(last_recorded_output)
                if not fallback_text:
                    reasoning_text = output_filter.get_reasoning_text()
                    fallback_text = _try_extract_answer_from_reasoning(reasoning_text)
                    if fallback_text:
                        self.logger.info(
                            "从推理链中提取到回答 (len=%d)",
                            len(fallback_text),
                            extra={"trace_id": trace_id, "category": "ai"} if trace_id else {"category": "ai"},
                        )
                
                fallback_output = sanitize_agent_output(
                    fallback_text,
                    self.settings.agent.fallback_text,
                )
                if fallback_output == self.settings.agent.fallback_text:
                    reason = "模型流未产生可见回复" if not fallback_text else "模型输出被安全过滤或为空"
                    self._log_agent_fallback(
                        trace_id=trace_id,
                        call_type=call_type,
                        chat_id=chat_id or "",
                        reason=reason,
                    )
                self._log_agent_answer(
                    trace_id=trace_id,
                    call_type=call_type,
                    chat_id=chat_id or "",
                    answer=fallback_output,
                    input_tokens=accumulated_input_tokens,
                    output_tokens=accumulated_output_tokens,
                )
                audit_status = "success"
                audit_final_answer = fallback_output
                yield fallback_output
                return

            final_answer = sanitize_agent_output(
                full_text,
                self.settings.agent.fallback_text,
            )
            if final_answer == self.settings.agent.fallback_text:
                self._log_agent_fallback(
                    trace_id=trace_id,
                    call_type=call_type,
                    chat_id=chat_id or "",
                    reason="模型流式输出被安全过滤或为空",
                )
            self._log_agent_answer(
                trace_id=trace_id,
                call_type=call_type,
                chat_id=chat_id or "",
                answer=final_answer,
                input_tokens=accumulated_input_tokens,
                output_tokens=accumulated_output_tokens,
            )
            audit_status = "success"
            audit_final_answer = final_answer

            if chat_id and bot_key and call_type != "draft":
                should_notify, notify_reason = _should_notify_owner(final_answer)
                if should_notify:
                    try:
                        await notify_owner(
                            content=user_query[:10000],
                            reason=notify_reason,
                            chat_id=chat_id,
                            bot_key=bot_key,
                            project_root=self.project_root,
                        )
                    except Exception:
                        _logger.warning("notify_owner failed", exc_info=True)

        except asyncio.CancelledError:
            audit_status = "cancelled"
            self._log_agent_fallback(
                trace_id=trace_id,
                call_type=call_type,
                chat_id=chat_id or "",
                reason="Agent 流式任务被取消",
            )
            return
        except Exception:
            log_kwargs = {"extra": {"trace_id": trace_id, "category": "ai"}} if trace_id else {"extra": {"category": "ai"}}
            self.logger.exception("Agent 流式工作流执行失败。", **log_kwargs)
            audit_status = "failed"
            self._log_agent_fallback(
                trace_id=trace_id,
                call_type=call_type,
                chat_id=chat_id or "",
                reason="Agent 流式工作流异常，返回降级回复",
            )
            if not collected_tokens:
                audit_final_answer = self.settings.agent.fallback_text
                yield self.settings.agent.fallback_text
            else:
                audit_final_answer = "".join(collected_tokens).strip() or self.settings.agent.fallback_text
            final_answer = self.settings.agent.fallback_text

        finally:
            try:
                reasoning_text = output_filter.get_reasoning_text()
                self.logger.debug(
                    "reasoning_debug: has_reasoning=%s len=%d collected_tokens=%d",
                    bool(reasoning_text),
                    len(reasoning_text),
                    len(collected_tokens),
                    extra={"trace_id": trace_id, "category": "ai"} if trace_id else {"category": "ai"},
                )
                if reasoning_text:
                    self._log_agent_reasoning(
                        trace_id=trace_id,
                        call_type=call_type,
                        chat_id=chat_id or "",
                        reasoning=reasoning_text,
                    )
                else:
                    # 检查是否显式关闭了思考模式
                    provider = self.settings.agent.providers.get(self.settings.agent.provider)
                    model_kwargs = dict(provider.model_kwargs or {}) if provider else {}
                    if (
                        ("reasoning_effort" in model_kwargs
                         and (model_kwargs["reasoning_effort"] is None or model_kwargs["reasoning_effort"] == ""))
                        or model_kwargs.get("enable_thinking") is False
                    ):
                        self._log_agent_reasoning(
                            trace_id=trace_id,
                            call_type=call_type,
                            chat_id=chat_id or "",
                            reasoning="已关闭思考模式",
                        )
            except Exception:
                pass
            if producer_task and not producer_task.done():
                producer_task.cancel()
                with suppress(asyncio.CancelledError):
                    await producer_task
            if audit_status == "started":
                audit_status = "cancelled" if cancel_check and cancel_check() else "failed"
                if not audit_final_answer and audit_status == "failed":
                    audit_final_answer = self.settings.agent.fallback_text
            if audit_status:
                self._write_memory_usage_audit(
                    trace_id=audit_trace_id,
                    chat_id=chat_id or "",
                    bot_key=bot_key,
                    call_type=call_type,
                    user_query=user_query,
                    memory_result=memory_result,
                    status=audit_status,
                    final_answer=audit_final_answer,
                    input_tokens=accumulated_input_tokens,
                    output_tokens=accumulated_output_tokens,
                )
            _current_chat_id.reset(chat_id_token)
            _current_bot_key.reset(bot_key_token)
            _current_project_root.reset(project_root_token)
            _current_trace_id.reset(trace_id_token)
            _current_call_type.reset(call_type_token)

    async def compress_context_if_needed(
        self,
        chat_id: str,
        *,
        sender_id: str = "",
        sender_name: str = "",
        bot_key: str = "",
        trace_id: str = "",
    ) -> dict[str, Any]:
        skip_reason, skip_message = get_context_compression_disabled_reason(
            database_path=self.database_path,
            chat_id=chat_id,
        )
        if skip_reason:
            return self._context_compression_skip_response(skip_reason, skip_message)

        context_sender = resolve_context_sender(
            database_path=self.database_path,
            chat_id=chat_id,
            sender_id=sender_id,
            sender_name=sender_name,
        )
        if not should_compress_context(
            database_path=self.database_path,
            chat_id=chat_id,
            sender_id=context_sender["sender_id"],
            settings=self.settings,
        ):
            return self._context_compression_skip_response("below_threshold", "当前无需压缩")

        from app.db.settings_store import load_settings_from_database
        platform_settings = load_settings_from_database(self.database_path)
        if platform_settings.agent.enabled:
            summary = await self.compress_context(
                chat_id,
                sender_id=context_sender["sender_id"],
                sender_name=context_sender["sender_name"],
                bot_key=bot_key,
                trace_id=trace_id,
            )
        else:
            platform_agent_service = AgentService(platform_settings, project_root=self.project_root)
            platform_agent_service.database_path = self.database_path
            platform_agent_service.logger = self.logger
            summary = await platform_agent_service.compress_context(
                chat_id,
                sender_id=context_sender["sender_id"],
                sender_name=context_sender["sender_name"],
                bot_key=bot_key,
                trace_id=trace_id,
            )
        return {"triggered": True, "skipped": False, "compressed": bool(summary), "summary": summary or "", "error": ""}

    async def compress_context(
        self,
        chat_id: str,
        *,
        sender_id: str = "",
        sender_name: str = "",
        bot_key: str = "",
        trace_id: str = "",
    ) -> str:
        skip_reason, _skip_message = get_context_compression_disabled_reason(
            database_path=self.database_path,
            chat_id=chat_id,
        )
        if skip_reason:
            return ""

        context_sender = resolve_context_sender(
            database_path=self.database_path,
            chat_id=chat_id,
            sender_id=sender_id,
            sender_name=sender_name,
        )
        actual_trace_id = trace_id or str(uuid4())
        lock_id = acquire_chat_compress_lock(
            self.database_path,
            chat_id=chat_id,
            trace_id=actual_trace_id,
        )
        if not lock_id:
            await wait_for_chat_compress_unlock(
                self.database_path,
                chat_id=chat_id,
            )
            return ""

        try:
            return await self._compress_context_locked(
                chat_id,
                sender_id=context_sender["sender_id"],
                sender_name=context_sender["sender_name"],
                bot_key=bot_key,
                trace_id=actual_trace_id,
            )
        finally:
            release_chat_compress_lock(self.database_path, slot_id=lock_id)

    async def _compress_context_locked(
        self,
        chat_id: str,
        *,
        sender_id: str = "",
        sender_name: str = "",
        bot_key: str = "",
        trace_id: str = "",
    ) -> str:
        transcript, covered_count, last_at = build_compression_transcript(
            database_path=self.database_path,
            chat_id=chat_id,
            sender_id=sender_id,
        )
        if not transcript.strip() or covered_count <= 0:
            return ""

        # 获取会话信息用于日志
        chat_name = chat_id
        conversation = get_conversation(chat_id=chat_id, database_path=self.database_path)
        if conversation:
            chat_name = conversation.get("display_name") or conversation.get("chat_name") or chat_id

        actual_trace_id = trace_id or str(uuid4())
        question = f"压缩会话上下文，覆盖 {covered_count} 条消息"

        # 创建 AI 工作项
        create_ai_work_item(
            self.database_path,
            trace_id=actual_trace_id,
            chat_id=chat_id,
            chat_name=chat_name,
            question=question,
            stage="开始压缩",
        )

        # 记录开始日志
        try:
            detail_parts = [
                f"call_type=compress",
                f"chat_id={chat_id}",
                f"bot_key={bot_key}",
                "",
                "=" * 80,
                "【压缩任务】",
                "=" * 80,
                question,
                "",
                "=" * 80,
                "【待压缩内容预览】",
                "=" * 80,
                transcript[:2000] + ("..." if len(transcript) > 2000 else ""),
            ]
            self._write_agent_log(
                trace_id=actual_trace_id,
                source="agent.compress",
                message="开始压缩会话上下文",
                detail="\n".join(detail_parts),
            )
        except Exception:
            self.logger.exception("记录压缩日志失败", extra={"category": "ai"})

        # 纯压缩提示词，不含其他系统提示
        prompt = "\n".join(
            [
                "请将以下对话压缩为后续回复必须优先遵守的上下文摘要。",
                "以下对话已经按当前用户筛选，只能总结该用户与机器人之间的历史，不要引入同群其他成员。",
                "保留用户身份线索、业务事实、明确偏好、未完成事项、关键约束。",
                "去除寒暄和重复内容。用中文，结构清晰，最多 "
                f"{self.settings.agent.context.summary_max_chars} 字。",
                "",
                transcript,
            ]
        )

        update_ai_work_item(
            self.database_path,
            trace_id=actual_trace_id,
            status="running",
            stage="调用模型压缩中",
        )

        try:
            # 直接构建模型并调用，不使用 Agent，避免夹杂其他提示词
            model = build_chat_model(self.settings)
            response = await asyncio.wait_for(
                model.ainvoke(prompt),
                timeout=self.settings.agent.timeout_seconds,
            )
            _record_tokens_from_response(
                response,
                database_path=self.database_path,
                settings=self.settings,
                call_type="compress",
                chat_id=chat_id,
                bot_key=bot_key,
            )
            summary = sanitize_agent_output(
                _extract_message_content(response),
                "",
                max_chars=self.settings.agent.context.summary_max_chars,
            )
        except asyncio.TimeoutError:
            timeout_message = (
                f"压缩会话上下文超时：超过 {self.settings.agent.timeout_seconds} 秒未返回，"
                "已跳过本次上下文摘要更新。"
            )
            self.logger.warning(
                timeout_message,
                extra={"category": "ai", "trace_id": actual_trace_id},
            )
            update_ai_work_item(
                self.database_path,
                trace_id=actual_trace_id,
                status="failed",
                error=timeout_message,
                stage="压缩超时",
            )
            try:
                detail_parts = [
                    "call_type=compress",
                    f"chat_id={chat_id}",
                    f"bot_key={bot_key}",
                    f"timeout_seconds={self.settings.agent.timeout_seconds}",
                    f"error={timeout_message}",
                ]
                self._write_agent_log(
                    trace_id=actual_trace_id,
                    source="agent.compress",
                    message="压缩会话上下文超时",
                    detail="\n".join(detail_parts),
                )
            except Exception:
                pass
            return ""
        except Exception as exc:
            self.logger.exception("压缩对话上下文失败。", extra={"category": "ai", "trace_id": actual_trace_id})
            update_ai_work_item(
                self.database_path,
                trace_id=actual_trace_id,
                status="failed",
                error=str(exc),
                stage="压缩失败",
            )
            # 记录失败日志
            try:
                detail_parts = [
                    f"call_type=compress",
                    f"chat_id={chat_id}",
                    f"error={str(exc)}",
                ]
                self._write_agent_log(
                    trace_id=actual_trace_id,
                    source="agent.compress",
                    message="压缩会话上下文失败",
                    detail="\n".join(detail_parts),
                )
            except Exception:
                pass
            return ""

        if summary:
            upsert_context_summary(
                database_path=self.database_path,
                chat_id=chat_id,
                sender_id=sender_id,
                summary=summary,
                covered_message_count=covered_count,
                last_message_at=last_at,
            )

        # 更新任务为完成
        update_ai_work_item(
            self.database_path,
            trace_id=actual_trace_id,
            status="completed",
            answer=summary,
            stage="完成",
        )

        # 记录完成日志
        try:
            detail_parts = [
                f"call_type=compress",
                f"chat_id={chat_id}",
                f"bot_key={bot_key}",
                "",
                "=" * 80,
                "【压缩结果】",
                "=" * 80,
                summary,
            ]
            self._write_agent_log(
                trace_id=actual_trace_id,
                source="agent.compress",
                message="压缩会话上下文完成",
                detail="\n".join(detail_parts),
            )
        except Exception:
            self.logger.exception("记录压缩完成日志失败", extra={"category": "ai"})

        return summary

    async def _get_agent(
        self,
        system_prompt: str = "",
        selection: RuntimeToolSelection | None = None,
        no_retry: bool = False,
    ) -> Any:
        if selection is None:
            selection = await self._select_runtime_tools("")

        model = build_chat_model(self.settings, no_retry=no_retry)
        tools = selection.tools
        current_tools_hash = _compute_tools_hash(tools)
        system_prompt_hash = hashlib.sha256(system_prompt.encode("utf-8", errors="ignore")).hexdigest()

        if current_tools_hash != self._tools_hash:
            self._agent_cache.clear()
            self._tools_hash = current_tools_hash

        cache_key = f"{current_tools_hash}:{system_prompt_hash}"
        if cache_key in self._agent_cache:
            self._agent_cache.move_to_end(cache_key)
            return self._agent_cache[cache_key]

        try:
            from langchain.agents import create_agent as _create_agent
        except ImportError:
            from langgraph.prebuilt import create_react_agent as _create_agent

        recursion_limit = max(25, int(self.settings.agent.max_iterations or 1) * 6)
        agent = _create_agent(
            model=model,
            tools=tools,
            system_prompt=system_prompt,
            debug=False,
            name="wecom-bot-agent",
        ).with_config({"recursion_limit": recursion_limit})

        self._agent_cache[cache_key] = agent
        if len(self._agent_cache) > self.settings.agent.max_cache_size:
            self._agent_cache.popitem(last=False)

        return agent

    async def _invoke_agent_with_event_logs(
        self,
        *,
        agent: Any,
        agent_input: dict[str, Any],
        trace_id: str,
        call_type: str,
        chat_id: str,
        bot_key: str,
        cancel_check: Callable[[], bool] | None = None,
        no_output_limit: bool = False,
    ) -> tuple[str, int, int]:
        final_result: Any = None
        last_recorded_output: Any = None
        last_non_notify_tool_output: Any = None
        recorded_model_outputs: set[int] = set()
        accumulated_input_tokens = 0
        accumulated_output_tokens = 0
        output_filter = _HiddenReasoningStreamFilter(
            max_reasoning_chars=self.settings.agent.max_reasoning_chars,
            truncation_notice=self.settings.agent.reasoning_truncation_notice,
        )

        async for event in agent.astream_events(agent_input, version="v2"):
            if cancel_check and cancel_check():
                raise CancelledError()

            kind = event.get("event", "")
            name = event.get("name", "")

            if kind == "on_chat_model_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk is not None:
                    _extract_and_collect_reasoning(chunk, output_filter)
            elif kind == "on_chat_model_end":
                output = event.get("data", {}).get("output")
                if output is not None:
                    last_recorded_output = output
                    recorded_model_outputs.add(id(output))
                    evt_tokens = _extract_usage_metadata(output)
                    accumulated_input_tokens += evt_tokens.get("input_tokens", 0)
                    accumulated_output_tokens += evt_tokens.get("output_tokens", 0)
                    _record_tokens_from_response(
                        output,
                        database_path=self.database_path,
                        settings=self.settings,
                        call_type=call_type,
                        chat_id=chat_id,
                        bot_key=bot_key,
                        trace_id=trace_id,
                    )
                    _extract_and_collect_reasoning(output, output_filter)
            elif kind == "on_chain_stream":
                chunk = event.get("data", {}).get("chunk")
                if chunk is None:
                    chunk = event.get("data", {}).get("output")
                if name == "LangGraph" and chunk is not None:
                    final_result = chunk
                    last_recorded_output = chunk
                    _extract_and_collect_reasoning(chunk, output_filter)
            elif kind == "on_chain_end":
                output = event.get("data", {}).get("output")
                if name == "model" and isinstance(output, list) and output and id(output[-1]) not in recorded_model_outputs:
                    last_recorded_output = output[-1]
                    evt_tokens = _extract_usage_metadata(output[-1])
                    accumulated_input_tokens += evt_tokens.get("input_tokens", 0)
                    accumulated_output_tokens += evt_tokens.get("output_tokens", 0)
                    _record_tokens_from_result(
                        {"messages": output},
                        database_path=self.database_path,
                        settings=self.settings,
                        call_type=call_type,
                        chat_id=chat_id,
                        bot_key=bot_key,
                        trace_id=trace_id,
                    )
                if name == "LangGraph" and output is not None:
                    final_result = output
                    _extract_and_collect_reasoning(output, output_filter)
            elif kind == "on_tool_start":
                self._log_agent_tool_event(
                    trace_id=trace_id,
                    phase="start",
                    tool_name=str(event.get("name", "unknown")),
                    payload=event.get("data", {}).get("input"),
                )
            elif kind == "on_tool_end":
                tool_name = str(event.get("name", "unknown"))
                tool_output = event.get("data", {}).get("output", "")
                if tool_output and not _is_notify_tool_name(tool_name):
                    last_non_notify_tool_output = tool_output
                self._log_agent_tool_event(
                    trace_id=trace_id,
                    phase="end",
                    tool_name=tool_name,
                    payload=tool_output,
                )

        reasoning_text = output_filter.get_reasoning_text().strip()
        if reasoning_text:
            self._log_agent_reasoning(
                trace_id=trace_id,
                call_type=call_type,
                chat_id=chat_id,
                reasoning=reasoning_text,
            )
        else:
            # 检查是否显式关闭了思考模式
            provider = self.settings.agent.providers.get(self.settings.agent.provider)
            model_kwargs = dict(provider.model_kwargs or {}) if provider else {}
            if (
                ("reasoning_effort" in model_kwargs
                 and (model_kwargs["reasoning_effort"] is None or model_kwargs["reasoning_effort"] == ""))
                or model_kwargs.get("enable_thinking") is False
            ):
                self._log_agent_reasoning(
                    trace_id=trace_id,
                    call_type=call_type,
                    chat_id=chat_id,
                    reasoning="已关闭思考模式",
                )

        if accumulated_input_tokens == 0 and accumulated_output_tokens == 0:
            if final_result is not None:
                _record_tokens_from_result(
                    final_result,
                    database_path=self.database_path,
                    settings=self.settings,
                    call_type=call_type,
                    chat_id=chat_id,
                    bot_key=bot_key,
                    trace_id=trace_id,
                )
                final_tokens = _extract_usage_metadata(final_result)
                accumulated_input_tokens = final_tokens.get("input_tokens", 0)
                accumulated_output_tokens = final_tokens.get("output_tokens", 0)
            elif last_recorded_output is not None:
                _record_tokens_from_response(
                    last_recorded_output,
                    database_path=self.database_path,
                    settings=self.settings,
                    call_type=call_type,
                    chat_id=chat_id,
                    bot_key=bot_key,
                    trace_id=trace_id,
                )
                final_tokens = _extract_usage_metadata(last_recorded_output)
                accumulated_input_tokens = final_tokens.get("input_tokens", 0)
                accumulated_output_tokens = final_tokens.get("output_tokens", 0)

        answer = _extract_text(final_result)
        if not answer and last_recorded_output is not None:
            answer = _extract_message_content(last_recorded_output)
        if call_type == "bot_task" and _is_empty_agent_answer(answer):
            answer = _extract_task_tool_result_text(last_non_notify_tool_output)
        if call_type == "bot_task" and _is_empty_agent_answer(answer):
            answer = _try_extract_answer_from_reasoning(reasoning_text)
        sanitized = sanitize_agent_output(
            answer or "",
            self.settings.agent.fallback_text,
            max_chars=0 if no_output_limit else None,
        )
        return sanitized, accumulated_input_tokens, accumulated_output_tokens

    def _log_agent_prompt(
        self,
        *,
        trace_id: str,
        call_type: str,
        chat_id: str,
        user_input: MultimodalContent,
        context_prompt: str,
        chat_history: list[dict[str, Any]] | None = None,
        system_prompt: str,
        selection: RuntimeToolSelection,
    ) -> None:
        if not trace_id:
            return
        detail_parts = [
            f"call_type={call_type}",
            f"chat_id={chat_id or '<empty>'}",
            "",
            "=" * 80,
            "【用户输入】",
            "=" * 80,
            _stringify_user_input(user_input),
            "",
            "=" * 80,
            "【上下文摘要】",
            "=" * 80,
            context_prompt or "<empty>",
            "",
            "=" * 80,
            "【最近历史消息】",
            "=" * 80,
            _format_chat_history_for_log(chat_history),
            "",
            "=" * 80,
            "【工具选择】",
            "=" * 80,
            "\n".join(selection.diagnostics) if selection.diagnostics else "<none>",
            "",
            "=" * 80,
            "【最终系统提示词】",
            "=" * 80,
            (system_prompt or "<empty>"),
        ]
        detail = "\n".join(detail_parts)
        self._write_agent_log(trace_id=trace_id, source="agent.prompt", message="Agent prompt payload", detail=detail)

    def _log_agent_reasoning(
        self,
        *,
        trace_id: str,
        call_type: str,
        chat_id: str,
        reasoning: str,
    ) -> None:
        if not trace_id:
            return
        if not reasoning:
            return
        detail_parts = [
            f"call_type={call_type}",
            f"chat_id={chat_id or '<empty>'}",
            "",
            "=" * 80,
            "【Agent think】",
            "=" * 80,
            reasoning,
        ]
        detail = "\n".join(detail_parts)
        self._write_agent_log(trace_id=trace_id, source="agent.reasoning", message="Agent thinking chain", detail=detail)

    def _log_agent_answer(
        self,
        *,
        trace_id: str,
        call_type: str,
        chat_id: str,
        answer: str,
        input_tokens: int = 0,
        output_tokens: int = 0,
    ) -> None:
        if not trace_id:
            return
        detail_parts = [
            f"call_type={call_type}",
            f"chat_id={chat_id or '<empty>'}",
            f"input_tokens={input_tokens}",
            f"output_tokens={output_tokens}",
            "",
            "=" * 80,
            "【Agent 最终输出】",
            "=" * 80,
            (answer or "<empty>"),
        ]
        detail = "\n".join(detail_parts)
        self._write_agent_log(trace_id=trace_id, source="agent.answer", message="Agent final answer", detail=detail)

    def _log_agent_fallback(
        self,
        *,
        trace_id: str,
        call_type: str,
        chat_id: str,
        reason: str,
    ) -> None:
        if not trace_id:
            return
        detail_parts = [
            f"call_type={call_type}",
            f"chat_id={chat_id or '<empty>'}",
            f"reason={reason or '<empty>'}",
            f"fallback_text={self.settings.agent.fallback_text}",
        ]
        self._write_agent_log(
            trace_id=trace_id,
            source="agent.fallback",
            message="Agent fallback reply used",
            detail="\n".join(detail_parts),
        )

    def _log_agent_tool_event(
        self,
        *,
        trace_id: str,
        phase: str,
        tool_name: str,
        payload: Any,
    ) -> None:
        if not trace_id:
            return
        title = f"【工具调用：{tool_name}】{phase}"
        detail_parts = [
            f"tool_name={tool_name}",
            f"phase={phase}",
            "",
            "=" * 80,
            title,
            "=" * 80,
            "payload:\n" + _stringify_payload(payload),
        ]
        detail = "\n".join(detail_parts)
        self._write_agent_log(
            trace_id=trace_id,
            source="agent.tool",
            message=f"Agent tool {phase}",
            detail=detail,
        )

    def _write_agent_log(
        self,
        *,
        trace_id: str,
        source: str,
        message: str,
        detail: str,
    ) -> None:
        try:
            insert_project_log(
                self.database_path,
                level="INFO",
                category="ai",
                source=source,
                message=message,
                detail=detail,
                trace_id=trace_id,
            )
        except Exception:
            self.logger.exception("Agent runtime log persist failed.", extra={"trace_id": trace_id, "category": "ai"})

    async def _expand_query_terms(self, user_query: str, *, trace_id: str = "") -> list[str]:
        if not user_query or not _is_query_expansion_enabled(self.project_root):
            return []
        try:
            return await expand_query_with_llm(
                user_query,
                settings=self.settings,
                database_path=self.database_path,
                trace_id=trace_id,
            )
        except Exception:
            self.logger.debug("Query expansion failed, falling back to original query", exc_info=True)
            return []

    async def _select_runtime_tools(
        self,
        user_input: MultimodalContent,
        *,
        expanded_terms: list[str] | None = None,
    ) -> RuntimeToolSelection:
        user_input_text = _selection_text_from_user_input(user_input)
        return await select_runtime_tools(
            self.settings,
            project_root=self.project_root,
            user_input_text=user_input_text,
            expanded_terms=expanded_terms if expanded_terms else None,
        )

    async def _build_system_prompt(
        self,
        context_prompt: str = "",
        selection: RuntimeToolSelection | None = None,
        user_query: str = "",
        trace_id: str = "",
        expanded_terms: list[str] | None = None,
    ) -> tuple[str, dict[str, Any]]:
        selection = selection or RuntimeToolSelection(
            tools=[],
            skill_context="",
            diagnostics=[],
            prompt_instructions=[],
        )

        sections: list[tuple[str, str]] = []
        memory_result: dict[str, Any] = {
            "memory_pack": "",
            "selected_files": [],
            "selected_sections": [],
            "omitted_files": [],
            "token_budget_used_estimate": 0,
            "confidence": "",
            "needs_more_memory": False,
            "reason": "",
        }

        max_chars = int(_cfg("agent.system_prompt_max_chars"))

        workflow_prompt = build_system_workflow_prompt(project_root=self.project_root)
        sections.append(("底层工作流规则", workflow_prompt))

        try:
            memory_result = await read_memory(
                user_query,
                project_root=self.project_root,
                settings=self.settings,
                database_path=self.database_path,
                trace_id=trace_id,
                expanded_terms=expanded_terms,
            )
        except Exception as e:
            _logger.warning(f"Failed to read memory, skipping: {e}")

        raw_memory_pack = str(memory_result.get("memory_pack", "") or "").strip()
        memory_pack_for_prompt = _format_memory_pack_for_prompt(raw_memory_pack)
        if memory_pack_for_prompt:
            sections.append(("记忆包", memory_pack_for_prompt))

        if self.settings.agent.system_prompt.strip():
            sections.append(("Bot 自定义指令", self.settings.agent.system_prompt.strip()))

        if context_prompt:
            sections.append(("对话上下文", context_prompt))

        if selection.prompt_instructions:
            instructions_text = "\n".join(
                f"- {inst}" for inst in selection.prompt_instructions
                if inst and inst.strip()
            )
            if instructions_text:
                sections.append(("本轮执行约束", instructions_text))

        if selection.skill_context:
            sections.append(("Skill 指令", selection.skill_context))

        return _render_system_prompt_sections(sections, max_chars).strip(), memory_result


async def _wait_with_cancel(
    task: asyncio.Task[Any],
    *,
    timeout: int,
    cancel_check: Callable[[], bool] | None = None,
) -> Any:
    cancel_event = asyncio.Event()

    async def _poll_cancel():
        while not task.done() and not cancel_event.is_set():
            if cancel_check and cancel_check():
                cancel_event.set()
                return
            await asyncio.sleep(0.5)

    poll_task = asyncio.create_task(_poll_cancel()) if cancel_check else None
    try:
        result = await asyncio.wait_for(task, timeout=timeout)
        return result
    except asyncio.TimeoutError:
        task.cancel()
        with suppress(asyncio.CancelledError):
            await task
        raise
    finally:
        if poll_task and not poll_task.done():
            cancel_event.set()
            poll_task.cancel()
            with suppress(asyncio.CancelledError):
                await poll_task
        if cancel_check and cancel_check() and not task.done():
            task.cancel()
            with suppress(asyncio.CancelledError):
                await task
            raise asyncio.CancelledError()


async def test_agent_connection(settings: Settings) -> str:
    provider = settings.agent.providers.get(settings.agent.provider)

    request_info = {
        "provider_type": provider.type if provider else None,
        "model": provider.model if provider else None,
        "base_url": provider.base_url if provider else None,
        "timeout_seconds": settings.agent.timeout_seconds
    }

    model = build_chat_model(settings)

    try:
        from langchain_core.messages import HumanMessage
    except ImportError as exc:  # pragma: no cover
        raise RuntimeError("langchain-core 未安装。") from exc

    try:
        response = await asyncio.wait_for(
            model.ainvoke([HumanMessage(content="请回复 OK，用于连通性测试。")]),
            timeout=settings.agent.timeout_seconds,
        )
        _record_tokens_from_response(
            response,
            database_path=default_database_path(),
            settings=settings,
            call_type="test",
        )
        return _extract_message_content(response) or "OK"
    except Exception as exc:
        error_info = extract_error_info(exc)
        error_info["request_info"] = request_info
        raise RuntimeError(format_error_message(error_info)) from None


def _extract_text(result: Any) -> str:
    """从 Agent 调用结果中提取文本内容，支持字典、消息列表等多种结果格式。"""
    if isinstance(result, str):
        return result.strip()

    if isinstance(result, dict):
        messages = result.get("messages")
        if isinstance(messages, list) and messages:
            for msg in reversed(messages):
                msg_type = ""
                if isinstance(msg, dict):
                    msg_type = str(msg.get("type", "")).lower()
                else:
                    msg_type = str(getattr(msg, "type", "")).lower()
                if msg_type not in ("ai", "assistant"):
                    continue
                content = _extract_message_content(msg)
                if content:
                    return content
        
        output = result.get("output") or result.get("content") or result.get("answer")
        if isinstance(output, str):
            return output.strip()
        
        # 尝试查找其他可能的字段
        for key in ("messages", "output", "content", "answer", "text", "generation"):
            value = result.get(key)
            if value:
                if isinstance(value, str):
                    return value.strip()
                if isinstance(value, list) and value:
                    return _extract_message_content(value[-1])

    return _extract_message_content(result)


def _is_notify_tool_name(tool_name: str) -> bool:
    normalized = str(tool_name or "").strip().lower().replace("_", "-")
    return "notify-me" in normalized or normalized.endswith("notify") or "notify" in normalized


def _is_empty_agent_answer(text: Any) -> bool:
    value = str(text or "").strip()
    return not value or value.lower() == "none"


def _extract_task_tool_result_text(tool_output: Any) -> str:
    if tool_output is None:
        return ""
    text = _extract_message_content(tool_output)
    if not text:
        text = str(tool_output or "").strip()
    if not text:
        return ""

    candidates = [text]
    content_match = re.search(r"content=(['\"])(?P<content>.*?)(?<!\\)\1", text, re.DOTALL)
    if content_match:
        candidates.insert(0, content_match.group("content").strip())

    for candidate in candidates:
        rendered = _render_task_tool_json_result(candidate)
        if rendered:
            return rendered
    return text.strip()


def _render_task_tool_json_result(text: str) -> str:
    candidate = str(text or "").strip().strip("`").strip()
    if not candidate:
        return ""
    try:
        payload = json.loads(candidate)
    except (json.JSONDecodeError, TypeError, ValueError):
        return ""
    if not isinstance(payload, dict):
        return ""

    date_text = str(payload.get("date") or "").strip()
    weekday = str(payload.get("weekday_cn") or payload.get("weekday_en") or "").strip()
    time_text = str(payload.get("time") or "").strip()
    if date_text:
        suffix = f"（{weekday}）" if weekday else ""
        if time_text:
            return f"{date_text}{suffix} {time_text}"
        return f"{date_text}{suffix}"

    for key in ("answer", "result", "summary", "content", "text"):
        value = payload.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    return json.dumps(payload, ensure_ascii=False)


def _extract_and_collect_reasoning(output: Any, output_filter: _HiddenReasoningStreamFilter) -> None:
    if output is None:
        return
    # 1. 直接从对象属性获取 reasoning_content
    reasoning = getattr(output, "reasoning_content", None)
    # 2. 从 additional_kwargs 获取
    if not reasoning:
        additional_kwargs = getattr(output, "additional_kwargs", None)
        if isinstance(additional_kwargs, dict):
            reasoning = additional_kwargs.get("reasoning_content") or additional_kwargs.get("reasoning")
    # 3. 从字典获取
    if not reasoning and isinstance(output, dict):
        reasoning = output.get("reasoning_content") or output.get("reasoning")
        if not reasoning:
            additional_kwargs = output.get("additional_kwargs")
            if isinstance(additional_kwargs, dict):
                reasoning = additional_kwargs.get("reasoning_content") or additional_kwargs.get("reasoning")
    # 4. 从 content 列表中获取 type=reasoning 的项
    if not reasoning:
        content = getattr(output, "content", None)
        if content is None and isinstance(output, dict):
            content = output.get("content")
        if isinstance(content, list):
            for item in content:
                if isinstance(item, dict):
                    item_type = str(item.get("type", "")).strip().lower()
                    if item_type in ("reasoning", "thinking", "thought"):
                        text = item.get("text", "") or item.get("content", "")
                        if isinstance(text, str) and text:
                            output_filter.collect_reasoning_text(text)
            return
    # 5. 从嵌套的 messages 列表中获取
    if not reasoning:
        messages = getattr(output, "messages", None)
        if messages is None and isinstance(output, dict):
            messages = output.get("messages")
        if isinstance(messages, list):
            for msg in messages:
                _extract_and_collect_reasoning(msg, output_filter)
            return
    if isinstance(reasoning, str) and reasoning:
        output_filter.collect_reasoning_text(reasoning)
    elif isinstance(reasoning, list):
        for item in reasoning:
            if isinstance(item, str) and item:
                output_filter.collect_reasoning_text(item)
            elif isinstance(item, dict):
                text = item.get("text", "") or item.get("content", "")
                if isinstance(text, str) and text:
                    output_filter.collect_reasoning_text(text)


def _extract_message_content(message: Any) -> str:
    """从消息对象中提取内容文本，支持 LangChain 消息、字典、列表等多种格式。"""
    if hasattr(message, "update") and not isinstance(message, dict):
        update = getattr(message, "update", None)
        if isinstance(update, dict):
            messages = update.get("messages")
            if isinstance(messages, list) and messages:
                for msg in reversed(messages):
                    content = _extract_message_content(msg)
                    if content:
                        return content
            # Command.update 可能直接包含 content
            for key in ("content", "text", "output", "answer"):
                val = update.get(key)
                if isinstance(val, str) and val.strip():
                    return val.strip()
    
    # 尝试从对象属性获取
    content = getattr(message, "content", None)
    if content is None:
        content = getattr(message, "text", None)
    if content is None:
        content = getattr(message, "output", None)
    
    # 尝试从字典获取
    if content is None and isinstance(message, dict):
        content = message.get("content") or message.get("text") or message.get("output")
    
    if isinstance(content, str):
        return content.strip()

    if isinstance(content, list):
        parts: list[str] = []
        for item in content:
            if isinstance(item, str):
                parts.append(item)
            elif isinstance(item, dict):
                text = item.get("text") or item.get("content")
                if isinstance(text, str):
                    parts.append(text)
        return "\n".join(part.strip() for part in parts if part.strip())
    
    # 如果是完整的消息对象，尝试其他字段
    if isinstance(message, dict):
        for key in ("content", "text", "output", "answer", "generation"):
            val = message.get(key)
            if isinstance(val, str) and val.strip():
                return val.strip()
    
    # 最后尝试直接转换为字符串（但排除已知对象类型）
    try:
        str_val = str(message)
        if str_val and str_val.strip() and not str_val.startswith("<"):
            # 排除看起来像对象 repr 的字符串（如 "Command(...)")
            if not str_val.startswith("Command("):
                return str_val.strip()
    except Exception:
        pass

    return ""


_REASONING_ANSWER_PATTERNS = [
    re.compile(r"回复内容[：:]\s*\n((?:.*\n)*?)(?=(?:检查约束|验证|注意事项|生成回复|$))", re.IGNORECASE),
    re.compile(r"回复[：:]\s*\n((?:.*\n)*?)(?=(?:检查约束|验证|注意事项|生成回复|$))", re.IGNORECASE),
    re.compile(r"回答[：:]\s*\n((?:.*\n)*?)(?=(?:检查约束|验证|注意事项|生成回复|$))", re.IGNORECASE),
    re.compile(r"最终(?:回复|回答|结果)[：:]\s*\n((?:.*\n)*?)(?=(?:检查约束|验证|注意事项|生成回复|$))", re.IGNORECASE),
]


def _try_extract_answer_from_reasoning(reasoning_text: str) -> str:
    if not reasoning_text or len(reasoning_text) < 20:
        return ""
    for pattern in _REASONING_ANSWER_PATTERNS:
        match = pattern.search(reasoning_text)
        if match:
            answer = match.group(1).strip()
            if len(answer) >= 10:
                return answer
    return ""


def _strip_hidden_reasoning(text: str) -> str:
    if not text:
        return ""

    cleaned = _HIDDEN_REASONING_BLOCK_PATTERN.sub("", text)
    lower_cleaned = cleaned.lower()
    open_indexes = [
        lower_cleaned.find(open_tag)
        for open_tag, _ in _HIDDEN_REASONING_TAG_PAIRS
        if lower_cleaned.find(open_tag) >= 0
    ]
    if open_indexes:
        cleaned = cleaned[: min(open_indexes)]
    cleaned = _HIDDEN_REASONING_TAG_PATTERN.sub("", cleaned)
    return cleaned


def sanitize_agent_output(
    text: str,
    fallback_text: str,
    *,
    max_chars: int | None = None,
    truncation_notice: str | None = None,
) -> str:
    """清洗 Agent 输出文本，包括去除隐藏推理标签、控制字符、重复内容截断和长度限制。"""
    if max_chars is None:
        max_chars = _cfg("agent.max_output_chars")
    if truncation_notice is None:
        truncation_notice = _cfg("agent.truncation_notice")
    if not text:
        return fallback_text

    if _control_char_ratio(text) > 0.05:
        return fallback_text

    if text.count("\ufffd") >= 3 and _replacement_char_ratio(text) > 0.01:
        return fallback_text

    if _gibberish_ratio(text) > 0.4:
        return fallback_text

    cleaned = _strip_hidden_reasoning(text)
    cleaned = _strip_control_chars(cleaned).strip()
    if not cleaned:
        return fallback_text

    cleaned = _truncate_repeated_chunks(cleaned, truncation_notice=truncation_notice)
    cleaned = _truncate_repeated_lines(cleaned, truncation_notice=truncation_notice)

    if max_chars and len(cleaned) > max_chars:
        cleaned = f"{cleaned[:max_chars].rstrip()}\n\n{truncation_notice}"

    return cleaned or fallback_text


def _strip_control_chars(text: str) -> str:
    return "".join(
        char
        for char in text
        if char in {"\n", "\r", "\t"} or ord(char) >= 32
    )


def _control_char_ratio(text: str) -> float:
    if not text:
        return 0
    count = sum(
        1
        for char in text
        if char not in {"\n", "\r", "\t"} and ord(char) < 32
    )
    return count / len(text)


def _replacement_char_ratio(text: str) -> float:
    if not text:
        return 0
    return text.count("\ufffd") / len(text)


def _gibberish_ratio(text: str) -> float:
    if not text or len(text) < 20:
        return 0
    if len(text) > 4000:
        text = text[:4000]
    printable = "".join(c for c in text if c.isprintable() and c not in {"\n", "\r", "\t", " "})
    if not printable:
        return 0
    consecutive_non_word = 0
    max_consecutive = 0
    for c in printable:
        if c.isalnum() or "\u4e00" <= c <= "\u9fff" or "\u3040" <= c <= "\u309f" or "\u30a0" <= c <= "\u30ff":
            consecutive_non_word = 0
        else:
            consecutive_non_word += 1
            max_consecutive = max(max_consecutive, consecutive_non_word)
    if max_consecutive > len(printable) * 0.3:
        return max_consecutive / len(printable)
    cjk_chars: list[str] = []
    other_chars: list[str] = []
    for ch in printable:
        if "\u4e00" <= ch <= "\u9fff" or "\u3400" <= ch <= "\u4dbf" or "\u3000" <= ch <= "\u303f":
            cjk_chars.append(ch)
        elif ch.isalpha():
            other_chars.append(ch)
    if cjk_chars:
        unique_cjk = len(set(cjk_chars))
        cjk_diversity = unique_cjk / len(cjk_chars)
        if cjk_diversity > 0.95 and len(cjk_chars) > 100:
            return cjk_diversity
    if other_chars:
        unique_other = len(set(other_chars))
        other_diversity = unique_other / len(other_chars)
        if other_diversity > 0.85 and len(other_chars) > 50:
            return other_diversity
    return 0


def _truncate_repeated_chunks(text: str, *, truncation_notice: str = "[内容已截断]") -> str:
    compact = text.strip()
    if len(compact) < 90:
        return text

    max_chunk_size = min(300, len(compact) // 3)
    for size in range(30, max_chunk_size + 1):
        chunk = compact[:size]
        if chunk and compact.startswith(chunk * 3):
            return f"{chunk.rstrip()}\n\n{truncation_notice}"

    return text


def _truncate_repeated_lines(text: str, *, truncation_notice: str = "[内容已截断]") -> str:
    lines = text.splitlines()
    nonempty = [_normalize_line(line) for line in lines if _normalize_line(line)]
    if len(nonempty) < 4:
        return text

    kept: list[str] = []
    seen: dict[str, int] = {}
    previous = ""
    consecutive = 0

    for line in lines:
        normalized = _normalize_line(line)
        if not normalized:
            kept.append(line)
            continue

        if normalized == previous:
            consecutive += 1
        else:
            previous = normalized
            consecutive = 1

        seen[normalized] = seen.get(normalized, 0) + 1
        if consecutive >= 3 or seen[normalized] > 3:
            kept.append("")
            kept.append(truncation_notice)
            return "\n".join(kept).strip()

        kept.append(line)

    unique_ratio = len(set(nonempty)) / len(nonempty)
    if len(nonempty) >= 8 and unique_ratio < 0.35:
        unique_lines: list[str] = []
        seen_unique: set[str] = set()
        for line in lines:
            normalized = _normalize_line(line)
            if not normalized or normalized in seen_unique:
                continue
            seen_unique.add(normalized)
            unique_lines.append(line)
        return "\n".join(unique_lines[:6]).strip() + f"\n\n{truncation_notice}"

    return text


def _normalize_line(line: str) -> str:
    return " ".join(line.strip().split())


def _build_agent_input(
    user_input: MultimodalContent,
    chat_history: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    """构建 Agent 输入字典，将用户输入和聊天历史转换为 LangChain 消息列表。"""
    from langchain_core.messages import AIMessage, HumanMessage

    messages: list[Any] = []
    if chat_history:
        for item in chat_history:
            content = str(item.get("content") or "").strip()
            if not content:
                continue
            direction = str(item.get("direction") or "")
            if direction == "user":
                messages.append(HumanMessage(content=content))
            elif direction == "bot":
                messages.append(AIMessage(content=content))

    messages.append(HumanMessage(content=user_input))
    return {"messages": messages}


def _selection_text_from_user_input(user_input: MultimodalContent) -> str:
    if isinstance(user_input, str):
        return user_input

    parts: list[str] = []
    for item in user_input:
        if not isinstance(item, dict):
            continue
        item_type = str(item.get("type", "")).strip().lower()
        if item_type == "text":
            parts.append(str(item.get("text") or ""))
        elif item_type:
            parts.append(f"[{item_type}]")
    return "\n".join(part for part in parts if part).strip()


def _format_chat_history_for_log(chat_history: list[dict[str, Any]] | None) -> str:
    if not chat_history:
        return "<empty>"

    lines: list[str] = []
    for index, item in enumerate(chat_history, 1):
        direction = str(item.get("direction") or "").strip() or "unknown"
        sender_name = str(item.get("custom_display_name") or item.get("sender_name") or "").strip()
        created_at = str(item.get("created_at") or "").strip()
        content = str(item.get("content") or "").strip()
        if len(content) > 1200:
            content = content[:1192].rstrip() + "\n[已截断]"

        header_parts = [f"{index}.", direction]
        if sender_name:
            header_parts.append(f"sender={sender_name}")
        if created_at:
            header_parts.append(f"created_at={created_at}")
        lines.append(" ".join(header_parts))
        lines.append(content or "<empty>")

    return "\n".join(lines).strip()


def _stringify_user_input(user_input: MultimodalContent) -> str:
    if isinstance(user_input, str):
        return user_input
    return _stringify_payload(user_input)


def _stringify_payload(payload: Any) -> str:
    if payload is None:
        return "<empty>"
    if isinstance(payload, str):
        return payload
    try:
        return json.dumps(payload, ensure_ascii=False, indent=2, default=str)
    except TypeError:
        return str(payload)


def _extract_usage_metadata(obj: Any) -> dict[str, int]:
    return extract_token_usage(obj)


def _get_provider_info(settings: Settings) -> dict[str, str]:
    provider = settings.agent.providers.get(settings.agent.provider)
    if provider is None:
        return {"provider_key": "", "provider_type": "", "model": ""}
    return {
        "provider_key": settings.agent.provider,
        "provider_type": provider.type,
        "model": provider.model,
    }


def _record_tokens_from_result(
    result: Any,
    *,
    database_path: Path,
    settings: Settings,
    call_type: str,
    chat_id: str = "",
    bot_key: str = "",
    trace_id: str = "",
    prompt_text: Any = "",
) -> dict[str, int]:
    raw = result
    if isinstance(result, dict) and "_raw_response" in result:
        raw = result["_raw_response"]
    elif isinstance(result, dict) and "messages" in result:
        messages = result.get("messages", [])
        if messages:
            raw = messages[-1]

    tokens, _ = resolve_token_usage(raw, prompt_text)
    if tokens["total_tokens"] > 0:
        provider_info = _get_provider_info(settings)
        try:
            record_token_usage(
                database_path,
                provider_key=provider_info["provider_key"],
                provider_type=provider_info["provider_type"],
                model=provider_info["model"],
                call_type=call_type,
                chat_id=chat_id,
                bot_key=bot_key,
                trace_id=trace_id,
                input_tokens=tokens["input_tokens"],
                output_tokens=tokens["output_tokens"],
                total_tokens=tokens["total_tokens"],
            )
        except Exception:
            _logger.warning("Token 使用记录写入失败。", extra={"category": "ai"}, exc_info=True)
    return tokens


def _compute_tools_hash(tools: list[Any]) -> str:
    if not tools:
        return ""
    signatures: list[str] = []
    for tool in tools:
        metadata = getattr(tool, "metadata", {}) or {}
        if not isinstance(metadata, dict):
            metadata = {}
        normalized_metadata = {
            str(key): str(value)
            for key, value in sorted(metadata.items(), key=lambda item: str(item[0]))
        }
        signatures.append(
            json.dumps(
                {
                    "name": getattr(tool, "name", str(tool)),
                    "description": getattr(tool, "description", ""),
                    "metadata": normalized_metadata,
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        )
    return hashlib.sha256("||".join(sorted(signatures)).encode("utf-8")).hexdigest()


def _record_tokens_from_response(
    response: Any,
    *,
    database_path: Path,
    settings: Settings,
    call_type: str,
    chat_id: str = "",
    bot_key: str = "",
    trace_id: str = "",
    prompt_text: Any = "",
) -> dict[str, int]:
    tokens, _ = resolve_token_usage(response, prompt_text)
    if tokens["total_tokens"] <= 0:
        return tokens

    provider_info = _get_provider_info(settings)
    try:
        record_token_usage(
            database_path,
            provider_key=provider_info["provider_key"],
            provider_type=provider_info["provider_type"],
            model=provider_info["model"],
            call_type=call_type,
            chat_id=chat_id,
            bot_key=bot_key,
            trace_id=trace_id,
            input_tokens=tokens["input_tokens"],
            output_tokens=tokens["output_tokens"],
            total_tokens=tokens["total_tokens"],
        )
    except Exception:
        _logger.warning("Token 使用记录写入失败（stream）。", extra={"category": "ai"}, exc_info=True)
    return tokens


_CANNOT_ANSWER_PATTERNS: list[tuple[re.Pattern[str], str]] = [
    (re.compile(r'(?:我|暂时)?无法回答', re.IGNORECASE), "回答中包含'无法回答'"),
    (re.compile(r'抱歉[，,]?\s*(?:我|暂时)?(?:不能|无法)', re.IGNORECASE), "回答中包含拒绝性表述"),
]


def _should_notify_owner(agent_output: str) -> tuple[bool, str]:
    if not agent_output or not agent_output.strip():
        return False, ""
    for pattern, reason in _CANNOT_ANSWER_PATTERNS:
        if pattern.search(agent_output):
            return True, reason
    return False, ""
