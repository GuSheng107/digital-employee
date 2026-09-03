from __future__ import annotations

from contextlib import AbstractAsyncContextManager, AsyncExitStack

from app.core.contracts import ErrorCode, RuntimeError, ToolCall, ToolResult, ToolSpec
from app.core.definitions import AgentDefinition, DefinitionStore, Settings
from app.tools.mcp_stdio import MCPStdioSession
from app.tools.skill_executor import SkillToolExecutor
from app.tools.skills import SkillLoader


class BoundToolRegistry(AbstractAsyncContextManager["BoundToolRegistry"]):
    def __init__(self, agent: AgentDefinition, definitions: DefinitionStore, settings: Settings) -> None:
        self.agent = agent
        self.definitions = definitions
        self.settings = settings
        self._stack = AsyncExitStack()
        self._mcp_sessions: dict[str, MCPStdioSession] = {}
        self._skill_executor = SkillToolExecutor()
        self.tools: list[ToolSpec] = []

    async def __aenter__(self) -> BoundToolRegistry:
        names: set[str] = set()
        for tool in SkillLoader(self.definitions).load_tools(self.agent.allowed_skills):
            if tool.name in names:
                raise RuntimeError(ErrorCode.TOOL_EXECUTION_FAILED, f"重复的工具名称：{tool.name}")
            names.add(tool.name)
            self.tools.append(tool)
        for server_id in self.agent.allowed_mcp_servers:
            server = self.definitions.get_mcp_server(server_id)
            session = await self._stack.enter_async_context(MCPStdioSession(server, self.settings.tool_result_max_chars))
            self._mcp_sessions[server_id] = session
            for tool in session.tools:
                if tool.name in names:
                    raise RuntimeError(ErrorCode.TOOL_EXECUTION_FAILED, f"重复的工具名称：{tool.name}")
                names.add(tool.name)
                self.tools.append(tool)
        return self

    async def __aexit__(self, exc_type: object, exc: object, traceback: object) -> None:
        await self._stack.aclose()

    async def execute(self, call: ToolCall) -> ToolResult:
        matching = next((tool for tool in self.tools if tool.name == call.name), None)
        if matching is None:
            return ToolResult(
                tool_call_id=call.id,
                tool_name=call.name,
                status="error",
                content="该工具未被当前 Agent 授权。",
                error_code=ErrorCode.TOOL_NOT_ALLOWED,
            )
        try:
            from jsonschema import ValidationError, validate

            validate(instance=call.arguments, schema=matching.input_schema)
        except ValidationError as exc:
            return ToolResult(
                tool_call_id=call.id,
                tool_name=call.name,
                status="error",
                content=f"工具参数不符合 schema：{exc.message}",
                error_code=ErrorCode.TOOL_INVALID_ARGUMENTS,
            )
        if matching.source != "mcp":
            manifest = self.definitions.get_skill_manifest(matching.source_id)
            local_name = matching.name.removeprefix(f"skill_{matching.source_id}_")
            definition = next((item for item in manifest.tools if item.name == local_name), None)
            if definition is None:
                return ToolResult(
                    tool_call_id=call.id,
                    tool_name=call.name,
                    status="error",
                    content="Skill 工具定义不存在。",
                    error_code=ErrorCode.TOOL_NOT_ALLOWED,
                )
            return await self._skill_executor.execute(
                matching.source_id,
                local_name,
                definition.handler,
                call.arguments,
                call.id,
                matching.timeout_seconds,
            )
        return await self._mcp_sessions[matching.source_id].invoke(call.name, call.arguments, call.id)
