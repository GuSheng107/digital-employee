from __future__ import annotations

import json
import os
import sys
from pathlib import Path

from pydantic import BaseModel, Field


class ModelProfile(BaseModel):
    profile_id: str = "default"
    model: str
    api_key: str | None = None
    api_base: str | None = None
    timeout_seconds: float = Field(default=45.0, gt=0, le=300)
    max_retries: int = Field(default=1, ge=0, le=3)
    max_output_tokens: int | None = Field(default=None, gt=0)


class AgentDefinition(BaseModel):
    id: str
    name: str
    instructions: str
    model_profile: str = "default"
    allowed_mcp_servers: list[str] = Field(default_factory=list)
    allowed_skills: list[str] = Field(default_factory=list)
    required_tool_name: str | None = None


class MCPServerDefinition(BaseModel):
    id: str
    command: str
    args: list[str] = Field(default_factory=list)
    env: dict[str, str] = Field(default_factory=dict)
    timeout_seconds: float = Field(default=20.0, gt=0, le=120)


class SkillManifest(BaseModel):
    id: str
    version: str
    description: str = ""
    inject_instructions: bool = True
    tools: list[SkillToolDefinition] = Field(default_factory=list)


class SkillToolDefinition(BaseModel):
    name: str
    description: str
    input_schema: dict[str, object] = Field(default_factory=lambda: {"type": "object", "properties": {}})
    handler: str


class Settings(BaseModel):
    project_root: Path
    model: ModelProfile
    max_tool_rounds: int = Field(default=3, ge=1, le=10)
    tool_result_max_chars: int = Field(default=8_000, ge=200, le=100_000)

    @classmethod
    def from_environment(cls, project_root: Path) -> Settings:
        return cls(
            project_root=project_root,
            model=ModelProfile(
                model=os.getenv("MODEL_NAME", "openai/gpt-4o-mini"),
                api_key=os.getenv("MODEL_API_KEY") or None,
                api_base=os.getenv("MODEL_API_BASE") or None,
                timeout_seconds=float(os.getenv("MODEL_TIMEOUT_SECONDS", "45")),
            ),
            max_tool_rounds=int(os.getenv("MAX_TOOL_ROUNDS", "3")),
        )


class DefinitionStore:
    def __init__(self, project_root: Path) -> None:
        self.project_root = project_root

    def get_agent(self, agent_id: str) -> AgentDefinition:
        return AgentDefinition.model_validate(self._read_json(self.project_root / "config" / "agents" / f"{agent_id}.json"))

    def list_agents(self) -> list[AgentDefinition]:
        directory = self.project_root / "config" / "agents"
        return [AgentDefinition.model_validate(self._read_json(path)) for path in sorted(directory.glob("*.json"))]

    def get_mcp_server(self, server_id: str) -> MCPServerDefinition:
        raw = self._read_json(self.project_root / "config" / "mcp" / f"{server_id}.json")
        raw["command"] = self._resolve_value(str(raw["command"]))
        raw["args"] = [self._resolve_value(str(value)) for value in raw.get("args", [])]
        raw["env"] = {key: self._resolve_value(str(value)) for key, value in raw.get("env", {}).items()}
        return MCPServerDefinition.model_validate(raw)

    def get_skill_manifest(self, skill_id: str) -> SkillManifest:
        return SkillManifest.model_validate(self._read_json(self.project_root / "skills" / skill_id / "skill.json"))

    def get_skill_instructions(self, skill_id: str) -> str:
        manifest = self.get_skill_manifest(skill_id)
        if not manifest.inject_instructions:
            return ""
        return (self.project_root / "skills" / skill_id / "SKILL.md").read_text(encoding="utf-8").strip()

    def _resolve_value(self, value: str) -> str:
        return value.replace("${PYTHON}", sys.executable).replace("${PROJECT_ROOT}", str(self.project_root))

    @staticmethod
    def _read_json(path: Path) -> dict[str, object]:
        if not path.is_file():
            raise FileNotFoundError(f"配置不存在：{path}")
        return json.loads(path.read_text(encoding="utf-8"))
