from __future__ import annotations

import asyncio
import json
from collections.abc import Awaitable, Callable
from uuid import uuid4

from app.core.contracts import ChatMessage, ErrorCode, RunEvent, RunRequest, RunResult, RuntimeError, SessionStore, ToolResult
from app.core.definitions import DefinitionStore, Settings
from app.infrastructure.model_gateway import ModelGateway
from app.infrastructure.recorder import JsonlRunRecorder
from app.tools.registry import BoundToolRegistry
from app.tools.skills import SkillLoader

EventSink = Callable[[RunEvent], Awaitable[None]]


class AgentRuntime:
    def __init__(
        self,
        settings: Settings,
        definitions: DefinitionStore,
        model_gateway: ModelGateway,
        recorder: JsonlRunRecorder,
        session_store: SessionStore | None = None,
    ) -> None:
        self.settings = settings
        self.definitions = definitions
        self.model_gateway = model_gateway
        self.recorder = recorder
        self.session_store = session_store
        self.skill_loader = SkillLoader(definitions)

    async def run(self, request: RunRequest, emit: EventSink | None = None) -> RunResult:
        run_id = str(uuid4())
        trace_id = str(uuid4())
        usage = {"prompt_tokens": 0, "completion_tokens": 0, "total_tokens": 0}
        session_id: str | None = request.conversation_id
        turn_id: str | None = None
        await self._emit(emit, RunEvent(type="run.started", run_id=run_id, trace_id=trace_id, data={"agent_id": request.agent_id}))
        self.recorder.record(trace_id, "run.started", {"run_id": run_id, "agent_id": request.agent_id})
        try:
            if self.session_store is not None:
                session_id, _ = self.session_store.ensure_session(
                    request.conversation_id,
                    user_id=request.user_id,
                    user_role=request.user_role,
                )
                turn_id = self.session_store.begin_turn(session_id, run_id, request.agent_id)
                persisted_history = self.session_store.load_messages(session_id)
                history = persisted_history or request.history
                self.session_store.append_message_event(
                    session_id,
                    ChatMessage(role="user", content=request.message),
                    event_type="user.message",
                    payload={"content": request.message},
                    turn_id=turn_id,
                    run_id=run_id,
                )
            else:
                history = request.history
            agent = self.definitions.get_agent(request.agent_id)
            profile = self.settings.model
            effective_request = request.model_copy(update={"conversation_id": session_id, "history": history})
            messages = self._build_messages(agent.instructions, agent.allowed_skills, effective_request)
            async with BoundToolRegistry(agent, self.definitions, self.settings) as tools:
                self.recorder.record(trace_id, "tools.bound", {"tools": [tool.name for tool in tools.tools]})
                await self._emit(emit, RunEvent(type="tools.bound", run_id=run_id, trace_id=trace_id, data={"tools": [tool.name for tool in tools.tools]}))
                for round_number in range(1, self.settings.max_tool_rounds + 1):
                    await self._emit(emit, RunEvent(type="model.started", run_id=run_id, trace_id=trace_id, data={"round": round_number}))
                    self.recorder.record(trace_id, "model.started", {"round": round_number, "model": profile.model})
                    if self.session_store is not None and session_id is not None:
                        self.session_store.append_event(
                            session_id,
                            "llm.request",
                            {"round": round_number, "model": profile.model, "message_count": len(messages)},
                            turn_id=turn_id,
                            run_id=run_id,
                        )
                    if round_number == 1 and agent.required_tool_name:
                        response = await asyncio.wait_for(
                            self.model_gateway.complete(messages, tools.tools, profile, tool_choice=agent.required_tool_name),
                            timeout=profile.timeout_seconds,
                        )
                    else:
                        response = await asyncio.wait_for(
                            self.model_gateway.complete(messages, tools.tools, profile),
                            timeout=profile.timeout_seconds,
                        )
                    self._add_usage(usage, response.usage)
                    self.recorder.record(
                        trace_id,
                        "model.completed",
                        {
                            "round": round_number,
                            "finish_reason": response.finish_reason,
                            "tool_calls": [call.name for call in response.tool_calls],
                            "usage": response.usage,
                        },
                    )
                    if self.session_store is not None and session_id is not None:
                        self.session_store.append_event(
                            session_id,
                            "llm.response",
                            {"round": round_number, "finish_reason": response.finish_reason, "usage": response.usage},
                            turn_id=turn_id,
                            run_id=run_id,
                        )
                    if not response.tool_calls:
                        if self.session_store is not None and session_id is not None and turn_id is not None:
                            self.session_store.append_message_event(
                                session_id,
                                ChatMessage(role="assistant", content=response.content),
                                event_type="assistant.message",
                                payload={"content": response.content},
                                turn_id=turn_id,
                                run_id=run_id,
                            )
                        result = RunResult(run_id=run_id, trace_id=trace_id, status="completed", conversation_id=session_id, answer=response.content, usage=usage)
                        await self._complete(emit, result)
                        return result

                    messages.append(ChatMessage(role="assistant", content=response.content, tool_calls=response.tool_calls))
                    if self.session_store is not None and session_id is not None and turn_id is not None:
                        self.session_store.append_message_event(
                            session_id,
                            ChatMessage(role="assistant", content=response.content, tool_calls=response.tool_calls),
                            event_type="assistant.message",
                            payload={"content": response.content, "tool_calls": [call.model_dump(mode="json") for call in response.tool_calls]},
                            turn_id=turn_id,
                            run_id=run_id,
                        )
                    for call in response.tool_calls:
                        if self.session_store is not None and session_id is not None:
                            self.session_store.append_event(
                                session_id,
                                "tool.call",
                                {"tool_call_id": call.id, "tool_name": call.name, "arguments": call.arguments},
                                turn_id=turn_id,
                                run_id=run_id,
                            )
                        await self._emit(emit, RunEvent(type="tool.started", run_id=run_id, trace_id=trace_id, data={"name": call.name, "arguments": call.arguments}))
                        tool_result = await tools.execute(call)
                        self._record_tool_result(trace_id, tool_result)
                        if self.session_store is not None and session_id is not None and turn_id is not None:
                            tool_message = ChatMessage(
                                role="tool",
                                tool_call_id=call.id,
                                content=json.dumps(tool_result.model_dump(mode="json"), ensure_ascii=False),
                            )
                            self.session_store.append_message_event(
                                session_id,
                                tool_message,
                                event_type="tool.result",
                                payload=tool_result.model_dump(mode="json"),
                                turn_id=turn_id,
                                run_id=run_id,
                            )
                        await self._emit(
                            emit,
                            RunEvent(
                                type="tool.completed",
                                run_id=run_id,
                                trace_id=trace_id,
                                data={"name": call.name, "status": tool_result.status, "error_code": tool_result.error_code},
                            ),
                        )
                        messages.append(
                            ChatMessage(
                                role="tool",
                                tool_call_id=call.id,
                                content=json.dumps(tool_result.model_dump(mode="json"), ensure_ascii=False),
                            )
                        )
                raise RuntimeError(ErrorCode.TOOL_LOOP_LIMIT, "工具调用超过最大轮数，已停止本次请求。")
        except asyncio.CancelledError:
            result = RunResult(run_id=run_id, trace_id=trace_id, status="cancelled", conversation_id=session_id, usage=usage, error_code=ErrorCode.RUN_CANCELLED, error_message="请求已取消。")
            self.recorder.record(trace_id, "run.cancelled", {})
            await self._complete(emit, result)
            return result
        except asyncio.TimeoutError:
            return await self._fail(emit, run_id, trace_id, usage, session_id, ErrorCode.MODEL_UNAVAILABLE, "模型调用超时。")
        except RuntimeError as exc:
            return await self._fail(emit, run_id, trace_id, usage, session_id, exc.code, exc.message)
        except FileNotFoundError as exc:
            return await self._fail(emit, run_id, trace_id, usage, session_id, ErrorCode.TOOL_EXECUTION_FAILED, str(exc))
        except Exception:
            return await self._fail(emit, run_id, trace_id, usage, session_id, ErrorCode.TOOL_EXECUTION_FAILED, "运行时发生未预期错误。")

    def _build_messages(self, instructions: str, skill_ids: list[str], request: RunRequest) -> list[ChatMessage]:
        messages = [ChatMessage(role="system", content=instructions)]
        messages.extend(ChatMessage(role="system", content=instruction) for instruction in self.skill_loader.load_instructions(skill_ids))
        messages.extend(request.history)
        messages.append(ChatMessage(role="user", content=request.message))
        return messages

    async def _fail(
        self,
        emit: EventSink | None,
        run_id: str,
        trace_id: str,
        usage: dict[str, int],
        session_id: str | None,
        code: ErrorCode,
        message: str,
    ) -> RunResult:
        result = RunResult(run_id=run_id, trace_id=trace_id, status="failed", conversation_id=session_id, usage=usage, error_code=code, error_message=message)
        self.recorder.record(trace_id, "run.failed", {"error_code": code, "message": message})
        if self.session_store is not None and session_id is not None:
            self.session_store.append_event(session_id, "error", {"error_code": code, "message": message}, run_id=run_id)
        await self._complete(emit, result)
        return result

    async def _complete(self, emit: EventSink | None, result: RunResult) -> None:
        event_type = {
            "completed": "run.completed",
            "failed": "run.failed",
            "cancelled": "run.cancelled",
        }[result.status]
        self.recorder.record(result.trace_id, event_type, {"status": result.status, "usage": result.usage, "error_code": result.error_code})
        if self.session_store is not None:
            self.session_store.finish_run(result.run_id, result.status)
        await self._emit(emit, RunEvent(type=event_type, run_id=result.run_id, trace_id=result.trace_id, data=result.model_dump(mode="json")))

    def _record_tool_result(self, trace_id: str, result: ToolResult) -> None:
        self.recorder.record(
            trace_id,
            "tool.completed",
            {"tool_name": result.tool_name, "status": result.status, "error_code": result.error_code, "content_chars": len(result.content)},
        )

    @staticmethod
    def _add_usage(total: dict[str, int], new_usage: dict[str, int]) -> None:
        for key in total:
            total[key] += int(new_usage.get(key, 0) or 0)

    @staticmethod
    async def _emit(emit: EventSink | None, event: RunEvent) -> None:
        if emit is not None:
            await emit(event)
