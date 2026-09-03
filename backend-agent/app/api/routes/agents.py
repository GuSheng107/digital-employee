"""Agent 运行时业务路由：模型调用、Agent 执行、Trace 与会话查询。"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from typing import cast

from fastapi import APIRouter, HTTPException, Query, Request
from fastapi.responses import StreamingResponse
from pydantic import BaseModel, Field

from app.core.agent_runtime import AgentRuntime
from app.core.contracts import ChatMessage, RunEvent, RunRequest, RuntimeError

router = APIRouter()


class RunInput(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    conversation_id: str | None = Field(default=None, max_length=200)
    user_id: str | None = Field(default=None, max_length=200)
    user_role: str | None = Field(default=None, max_length=100)


def _get_runtime(request: Request) -> AgentRuntime:
    """从应用状态中读取已初始化的 AgentRuntime。"""
    runtime = getattr(request.app.state, "agent_runtime", None)
    if not isinstance(runtime, AgentRuntime):
        raise HTTPException(status_code=503, detail="Agent 运行时尚未初始化")
    return runtime


@router.get("/agents")
async def list_agents(request: Request) -> dict[str, object]:
    runtime = _get_runtime(request)
    agents = runtime.definitions.list_agents()
    return {"agents": [{"id": agent.id, "name": agent.name} for agent in agents]}


@router.post("/model/test")
async def test_model(request: Request) -> dict[str, object]:
    runtime = _get_runtime(request)
    try:
        response = await runtime.model_gateway.complete(
            [ChatMessage(role="user", content="你好")],
            [],
            runtime.settings.model,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail={"error_code": exc.code, "message": exc.message}) from exc
    return {"ok": True, "model": runtime.settings.model.model, "answer": response.content, "usage": response.usage}


@router.post("/agents/{agent_id}/test")
async def run_agent(agent_id: str, payload: RunInput, request: Request) -> dict[str, object]:
    runtime = _get_runtime(request)
    result = await runtime.run(
        RunRequest(agent_id=agent_id, message=payload.message, history=payload.history, conversation_id=payload.conversation_id, user_id=payload.user_id, user_role=payload.user_role),
    )
    if result.status != "completed":
        raise HTTPException(status_code=502, detail=result.model_dump(mode="json"))
    return result.model_dump(mode="json")


@router.post("/agents/{agent_id}/stream")
async def stream_agent(agent_id: str, payload: RunInput, request: Request) -> StreamingResponse:
    runtime = _get_runtime(request)

    async def generate() -> AsyncIterator[str]:
        queue: asyncio.Queue[RunEvent | None] = asyncio.Queue()

        async def emit(event: RunEvent) -> None:
            await queue.put(event)

        task = asyncio.create_task(
            runtime.run(
                RunRequest(agent_id=agent_id, message=payload.message, history=payload.history, conversation_id=payload.conversation_id, user_id=payload.user_id, user_role=payload.user_role),
                emit=emit,
            )
        )
        try:
            while True:
                event = await queue.get()
                if event is None:
                    break
                yield f"event: {event.type}\ndata: {event.model_dump_json()}\n\n"
                if event.type in {"run.completed", "run.failed"}:
                    break
        finally:
            if not task.done():
                task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    return StreamingResponse(generate(), media_type="text/event-stream")


@router.get("/traces/{trace_id}")
async def get_trace(trace_id: str, request: Request) -> dict[str, object]:
    runtime = _get_runtime(request)
    events = runtime.recorder.get_trace(trace_id)
    if not events:
        raise HTTPException(status_code=404, detail="trace 不存在")
    return {"trace_id": trace_id, "events": events}


@router.get("/sessions/{session_id}")
async def get_session(session_id: str, request: Request) -> dict[str, object]:
    runtime = _get_runtime(request)
    if runtime.session_store is None:
        raise HTTPException(status_code=503, detail="会话持久化未启用")
    session = runtime.session_store.get_session(session_id)
    if session is None:
        raise HTTPException(status_code=404, detail="会话不存在")
    return session


@router.get("/sessions")
async def list_sessions(
    request: Request,
    user_id: str | None = Query(default=None, max_length=200),
    limit: int = Query(default=50, ge=1, le=200),
) -> dict[str, object]:
    runtime = _get_runtime(request)
    if runtime.session_store is None:
        raise HTTPException(status_code=503, detail="会话持久化未启用")
    return {"sessions": cast(list[dict[str, object]], runtime.session_store.list_sessions(user_id=user_id, limit=limit))}
