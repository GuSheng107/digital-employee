from __future__ import annotations

import asyncio
import json
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field
from dotenv import load_dotenv

from app.core.contracts import ChatMessage, RunEvent, RunRequest, RuntimeError
from app.core.definitions import DefinitionStore, Settings
from app.core.runtime import AgentRuntime
from app.infrastructure.model_gateway import LiteLLMModelGateway
from app.infrastructure.recorder import JsonlRunRecorder

PROJECT_ROOT = Path(__file__).resolve().parents[1]


def create_runtime(project_root: Path = PROJECT_ROOT) -> AgentRuntime:
    load_dotenv(project_root / ".env")
    settings = Settings.from_environment(project_root)
    return AgentRuntime(
        settings=settings,
        definitions=DefinitionStore(project_root),
        model_gateway=LiteLLMModelGateway(),
        recorder=JsonlRunRecorder(project_root / "var" / "traces"),
    )


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    app.state.runtime = create_runtime()
    yield


app = FastAPI(title="Backend Agent Runtime", version="0.1.0", lifespan=lifespan)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["null", "http://127.0.0.1:8766", "http://localhost:8766"],
    allow_credentials=False,
    allow_methods=["GET", "POST", "OPTIONS"],
    allow_headers=["Content-Type"],
)
app.mount("/debug", StaticFiles(directory=PROJECT_ROOT / "app" / "static" / "debug", html=True), name="debug")


class RunInput(BaseModel):
    message: str = Field(min_length=1, max_length=20_000)
    history: list[ChatMessage] = Field(default_factory=list, max_length=20)
    conversation_id: str | None = Field(default=None, max_length=200)


@app.get("/health")
async def health() -> dict[str, str]:
    return {"status": "ok", "phase": "1"}


@app.get("/v1/agents")
async def list_agents(request: Request) -> dict[str, object]:
    runtime: AgentRuntime = request.app.state.runtime
    agents = runtime.definitions.list_agents()
    return {"agents": [{"id": agent.id, "name": agent.name} for agent in agents]}


@app.post("/v1/model/test")
async def test_model(request: Request) -> dict[str, object]:
    runtime: AgentRuntime = request.app.state.runtime
    try:
        response = await runtime.model_gateway.complete(
            [ChatMessage(role="user", content="你好")],
            [],
            runtime.settings.model,
        )
    except RuntimeError as exc:
        raise HTTPException(status_code=502, detail={"error_code": exc.code, "message": exc.message}) from exc
    return {"ok": True, "model": runtime.settings.model.model, "answer": response.content, "usage": response.usage}


@app.post("/v1/agents/{agent_id}/test")
async def run_agent(agent_id: str, payload: RunInput, request: Request) -> dict[str, object]:
    runtime: AgentRuntime = request.app.state.runtime
    result = await runtime.run(
        RunRequest(agent_id=agent_id, message=payload.message, history=payload.history, conversation_id=payload.conversation_id),
    )
    if result.status != "completed":
        raise HTTPException(status_code=502, detail=result.model_dump(mode="json"))
    return result.model_dump(mode="json")


@app.post("/v1/agents/{agent_id}/stream")
async def stream_agent(agent_id: str, payload: RunInput, request: Request) -> StreamingResponse:
    runtime: AgentRuntime = request.app.state.runtime

    async def generate() -> AsyncIterator[str]:
        queue: asyncio.Queue[RunEvent | None] = asyncio.Queue()

        async def emit(event: RunEvent) -> None:
            await queue.put(event)

        task = asyncio.create_task(
            runtime.run(
                RunRequest(agent_id=agent_id, message=payload.message, history=payload.history, conversation_id=payload.conversation_id),
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


@app.get("/v1/traces/{trace_id}")
async def get_trace(trace_id: str, request: Request) -> dict[str, object]:
    runtime: AgentRuntime = request.app.state.runtime
    events = runtime.recorder.get_trace(trace_id)
    if not events:
        raise HTTPException(status_code=404, detail="trace 不存在")
    return {"trace_id": trace_id, "events": events}
