"""Agent 运行时测试：生命周期管理与模型-工具执行循环。"""

from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

from app.core.agent_runtime import AgentRuntime
from app.core.contracts import ChatMessage, ModelResponse, RunRequest, ToolCall, ToolSpec
from app.core.definitions import DefinitionStore, ModelProfile, Settings
from app.core.runtime import RuntimeManager, RuntimeStatus
from app.infrastructure.recorder import JsonlRunRecorder


@pytest.mark.asyncio
async def test_runtime_start_and_stop_changes_status() -> None:
    """运行时应按顺序进入就绪和停止状态。"""
    runtime = RuntimeManager()
    assert runtime.status is RuntimeStatus.CREATED

    await runtime.start()
    assert runtime.status is RuntimeStatus.READY
    assert runtime.is_ready is True

    await runtime.stop()
    assert runtime.status is RuntimeStatus.STOPPED
    assert runtime.is_ready is False


@pytest.mark.asyncio
async def test_runtime_start_and_stop_are_idempotent() -> None:
    """重复启动和停止不应破坏状态。"""
    runtime = RuntimeManager()
    await runtime.start()
    await runtime.start()
    await runtime.stop()
    await runtime.stop()
    assert runtime.status is RuntimeStatus.STOPPED


class ScriptedWeatherGateway:
    def __init__(self) -> None:
        self.calls = 0
        self.first_call_tools: list[ToolSpec] = []

    async def complete(self, messages: list[ChatMessage], tools: list[ToolSpec], profile: ModelProfile) -> ModelResponse:
        self.calls += 1
        if self.calls == 1:
            self.first_call_tools = tools
            assert "北京今天天气怎样" in messages[-1].content
            return ModelResponse(tool_calls=[ToolCall(id="weather-call-1", name="mcp_weather_get_weather", arguments={"city": "北京"})])
        assert messages[-1].role == "tool"
        result = json.loads(messages[-1].content)
        assert result["status"] == "success"
        structured = result.get("structured_data") or {}
        assert "26" in result["content"] or structured.get("temperature_c") == 26.0
        return ModelResponse(content="北京当前晴，26.0 摄氏度。", usage={"prompt_tokens": 12, "completion_tokens": 8, "total_tokens": 20})


class UnknownToolGateway:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages: list[ChatMessage], tools: list[ToolSpec], profile: ModelProfile) -> ModelResponse:
        self.calls += 1
        if self.calls == 1:
            return ModelResponse(tool_calls=[ToolCall(id="bad-tool", name="mcp_weather_not_allowed", arguments={})])
        result = json.loads(messages[-1].content)
        assert result["error_code"] == "tool_not_allowed"
        return ModelResponse(content="该工具不可用。")


class SkillToolGateway:
    def __init__(self) -> None:
        self.calls = 0

    async def complete(self, messages: list[ChatMessage], tools: list[ToolSpec], profile: ModelProfile) -> ModelResponse:
        self.calls += 1
        if self.calls == 1:
            assert "skill_weather-assistant_format_weather_observation" in [tool.name for tool in tools]
            return ModelResponse(
                tool_calls=[
                    ToolCall(
                        id="format-call-1",
                        name="skill_weather-assistant_format_weather_observation",
                        arguments={"city": "北京", "weather": "晴", "temperature_c": 26},
                    )
                ]
            )
        result = json.loads(messages[-1].content)
        assert result["structured_data"]["summary"] == "北京：晴，26 摄氏度。"
        return ModelResponse(content=result["structured_data"]["summary"])


def write_test_project(tmp_path: Path) -> Path:
    (tmp_path / "config" / "agents").mkdir(parents=True)
    (tmp_path / "config" / "mcp").mkdir(parents=True)
    (tmp_path / "skills" / "weather-assistant").mkdir(parents=True)
    fixture = Path(__file__).parent / "fixtures" / "fake_weather_mcp.py"
    (tmp_path / "config" / "agents" / "weather-agent.json").write_text(
        json.dumps(
            {
                "id": "weather-agent",
                "name": "天气助手",
                "instructions": "需要天气时调用工具。",
                "allowed_mcp_servers": ["weather"],
                "allowed_skills": ["weather-assistant"],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "config" / "mcp" / "weather.json").write_text(
        json.dumps({"id": "weather", "command": sys.executable, "args": [str(fixture)], "timeout_seconds": 15}),
        encoding="utf-8",
    )
    (tmp_path / "skills" / "weather-assistant" / "skill.json").write_text(
        json.dumps(
            {
                "id": "weather-assistant",
                "version": "1.0.0",
                "tools": [
                    {
                        "name": "format_weather_observation",
                        "description": "格式化天气摘要",
                        "input_schema": {
                            "type": "object",
                            "required": ["city", "weather", "temperature_c"],
                            "properties": {
                                "city": {"type": "string"},
                                "weather": {"type": "string"},
                                "temperature_c": {"type": "number"},
                            },
                        },
                        "handler": "format_weather_observation",
                    }
                ],
            },
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )
    (tmp_path / "skills" / "weather-assistant" / "SKILL.md").write_text("使用天气工具。", encoding="utf-8")
    return tmp_path


def make_runtime(tmp_path: Path, gateway: object) -> AgentRuntime:
    root = write_test_project(tmp_path)
    return AgentRuntime(
        settings=Settings(project_root=root, model=ModelProfile(model="test", api_key="not-used")),
        definitions=DefinitionStore(root),
        model_gateway=gateway,  # type: ignore[arg-type]
        recorder=JsonlRunRecorder(root / "var" / "traces"),
    )


@pytest.mark.asyncio
async def test_runtime_calls_stdio_mcp_and_returns_model_answer(tmp_path: Path) -> None:
    gateway = ScriptedWeatherGateway()
    runtime = make_runtime(tmp_path, gateway)

    result = await runtime.run(RunRequest(agent_id="weather-agent", message="北京今天天气怎样"))

    assert result.status == "completed"
    assert result.answer == "北京当前晴，26.0 摄氏度。"
    assert result.usage["total_tokens"] == 20
    assert "mcp_weather_get_weather" in [tool.name for tool in gateway.first_call_tools]
    assert "skill_weather-assistant_format_weather_observation" in [tool.name for tool in gateway.first_call_tools]
    event_types = [event["type"] for event in runtime.recorder.get_trace(result.trace_id)]
    assert "tools.bound" in event_types
    assert "tool.completed" in event_types


@pytest.mark.asyncio
async def test_runtime_returns_unknown_tool_as_structured_tool_result(tmp_path: Path) -> None:
    gateway = UnknownToolGateway()
    runtime = make_runtime(tmp_path, gateway)

    result = await runtime.run(RunRequest(agent_id="weather-agent", message="测试未知工具"))

    assert result.status == "completed"
    assert result.answer == "该工具不可用。"
    assert gateway.calls == 2


@pytest.mark.asyncio
async def test_runtime_executes_explicitly_bound_skill_tool(tmp_path: Path) -> None:
    runtime = make_runtime(tmp_path, SkillToolGateway())

    result = await runtime.run(RunRequest(agent_id="weather-agent", message="格式化天气"))

    assert result.status == "completed"
    assert result.answer == "北京：晴，26 摄氏度。"
