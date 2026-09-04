from __future__ import annotations

import asyncio
from pathlib import Path

from test_runtime import write_test_project

from app.core.contracts import ChatMessage, ModelResponse, RunRequest
from app.core.definitions import DefinitionStore, ModelProfile, Settings
from app.core.agent_runtime import AgentRuntime
from app.infrastructure.recorder import JsonlRunRecorder
from app.infrastructure.session_store import SQLiteSessionStore


def test_sqlite_store_reopens_with_session_messages_and_reserved_role(tmp_path: Path) -> None:
    database = tmp_path / "var" / "sessions.sqlite3"
    store = SQLiteSessionStore(database)
    session_id, created = store.ensure_session("session-1", user_id="user-1", user_role="operator")
    assert created is True
    turn_id = store.begin_turn(session_id, "run-1", "weather-agent")
    store.append_message_event(
        session_id,
        ChatMessage(role="user", content="你好"),
        event_type="user.message",
        payload={"content": "你好"},
        turn_id=turn_id,
        run_id="run-1",
    )
    store.append_message_event(
        session_id,
        ChatMessage(role="assistant", content="你好，有什么可以帮你？"),
        event_type="assistant.message",
        payload={"content": "你好，有什么可以帮你？"},
        turn_id=turn_id,
        run_id="run-1",
    )
    store.finish_run("run-1", "completed")
    store.close()

    reopened = SQLiteSessionStore(database)
    session = reopened.get_session("session-1")
    assert session is not None
    assert session["user_id"] == "user-1"
    assert session["user_role"] == "operator"
    assert [message["content"] for message in session["messages"]] == ["你好", "你好，有什么可以帮你？"]
    assert session["turns"][0]["status"] == "completed"
    assert [event["type"] for event in session["events"]] == [
        "session.created",
        "turn.started",
        "run.started",
        "user.message",
        "assistant.message",
        "run.completed",
        "turn.completed",
    ]
    reopened.close()


def test_sqlite_store_lists_sessions_by_user_with_first_message(tmp_path: Path) -> None:
    store = SQLiteSessionStore(tmp_path / "var" / "sessions.sqlite3")
    first_id, _ = store.ensure_session("first", user_id="debug-user")
    first_turn = store.begin_turn(first_id, "run-first", "weather-agent")
    store.append_message_event(
        first_id,
        ChatMessage(role="user", content="北京天气怎么样"),
        event_type="user.message",
        payload={"content": "北京天气怎么样"},
        turn_id=first_turn,
        run_id="run-first",
    )
    second_id, _ = store.ensure_session("second", user_id="other-user")
    second_turn = store.begin_turn(second_id, "run-second", "weather-agent")
    store.append_message_event(
        second_id,
        ChatMessage(role="user", content="上海天气怎么样"),
        event_type="user.message",
        payload={"content": "上海天气怎么样"},
        turn_id=second_turn,
        run_id="run-second",
    )

    sessions = store.list_sessions(user_id="debug-user")

    assert len(sessions) == 1
    assert sessions[0]["id"] == "first"
    assert sessions[0]["first_message"] == "北京天气怎么样"
    assert sessions[0]["first_message_at"]
    store.close()


class RecordingGateway:
    def __init__(self) -> None:
        self.messages_by_call: list[list[ChatMessage]] = []

    async def complete(self, messages: list[ChatMessage], tools: list[object], profile: ModelProfile) -> ModelResponse:
        self.messages_by_call.append(messages.copy())
        return ModelResponse(content=f"收到：{messages[-1].content}")


def test_runtime_restores_history_and_keeps_role_as_reserved_metadata(tmp_path: Path) -> None:
    root = write_test_project(tmp_path)
    gateway = RecordingGateway()
    store = SQLiteSessionStore(root / "var" / "sessions.sqlite3")
    runtime = AgentRuntime(
        settings=Settings(project_root=root, model=ModelProfile(model="test", api_key="not-used")),
        definitions=DefinitionStore(root),
        model_gateway=gateway,  # type: ignore[arg-type]
        recorder=JsonlRunRecorder(root / "var" / "traces"),
        session_store=store,
    )

    first = asyncio.run(runtime.run(RunRequest(agent_id="weather-agent", message="第一条", user_id="user-1", user_role="operator")))
    store.close()
    reopened_store = SQLiteSessionStore(root / "var" / "sessions.sqlite3")
    restarted_runtime = AgentRuntime(
        settings=Settings(project_root=root, model=ModelProfile(model="test", api_key="not-used")),
        definitions=DefinitionStore(root),
        model_gateway=gateway,  # type: ignore[arg-type]
        recorder=JsonlRunRecorder(root / "var" / "traces"),
        session_store=reopened_store,
    )
    second = asyncio.run(
        restarted_runtime.run(
            RunRequest(
                agent_id="weather-agent",
                message="第二条",
                conversation_id=first.conversation_id,
                user_id="user-2",
                user_role="viewer",
            )
        )
    )

    assert first.status == "completed"
    assert second.status == "completed"
    assert second.conversation_id == first.conversation_id
    second_contents = [message.content for message in gateway.messages_by_call[1]]
    assert "第一条" in second_contents
    assert "收到：第一条" in second_contents
    assert second_contents[-1] == "第二条"
    session = reopened_store.get_session(first.conversation_id or "")
    assert session is not None
    assert session["user_id"] == "user-1"
    assert session["user_role"] == "operator"
    assert [message["role"] for message in session["messages"]] == ["user", "assistant", "user", "assistant"]
    assert len(session["events"]) > 10
    reopened_store.close()
