"""AI Agent 运行时包，提供核心 Agent 服务，包括 LLM 交互、工具选择、命令分发和流式编排。"""
from agent_runtime.service import AgentService, sanitize_agent_output
from agent_runtime.commands import SystemCommand, is_command_attempt, match_system_command, dispatch_system_command
from agent_runtime.capabilities import ModelCapability, get_model_capabilities, detect_capabilities_api
from agent_runtime.prompts import build_system_workflow_prompt, SYSTEM_WORKFLOW_PROMPT

__all__ = [
    "AgentService",
    "sanitize_agent_output",
    "SystemCommand",
    "is_command_attempt",
    "match_system_command",
    "dispatch_system_command",
    "ModelCapability",
    "get_model_capabilities",
    "detect_capabilities_api",
    "build_system_workflow_prompt",
    "SYSTEM_WORKFLOW_PROMPT",
]
