from __future__ import annotations

import re

from app.core.contracts import ToolSpec
from app.core.definitions import DefinitionStore


class SkillLoader:
    def __init__(self, definitions: DefinitionStore) -> None:
        self.definitions = definitions

    def load_instructions(self, skill_ids: list[str]) -> list[str]:
        instructions: list[str] = []
        for skill_id in skill_ids:
            manifest = self.definitions.get_skill_manifest(skill_id)
            body = self.definitions.get_skill_instructions(skill_id)
            if body:
                instructions.append(f"[Skill: {manifest.id} v{manifest.version}]\n{body}")
        return instructions

    def load_tools(self, skill_ids: list[str]) -> list[ToolSpec]:
        tools: list[ToolSpec] = []
        for skill_id in skill_ids:
            manifest = self.definitions.get_skill_manifest(skill_id)
            for tool in manifest.tools:
                tools.append(
                    ToolSpec(
                        name=re.sub(r"[^a-zA-Z0-9_-]", "_", f"skill_{manifest.id}_{tool.name}")[:64],
                        description=tool.description,
                        input_schema=tool.input_schema,
                        source="skill",
                        source_id=manifest.id,
                    )
                )
        return tools
