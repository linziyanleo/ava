"""Agent adapter registry."""

from __future__ import annotations

from ava.agents.adapter import AgentAdapter
from ava.agents.claude_code.adapter import ClaudeCodeAdapter
from ava.agents.codex.adapter import CodexAdapter
from ava.agents.image_gen.adapter import ImageGenAdapter
from ava.agents.nanobot.adapter import NanobotAdapter
from ava.agents.process_manager import AgentProcessManager, HealthStatus, ProcessHandle


def default_agent_adapters() -> list[AgentAdapter]:
    return [
        NanobotAdapter(),
        ClaudeCodeAdapter(),
        CodexAdapter(),
        ImageGenAdapter(),
    ]


__all__ = [
    "AgentAdapter",
    "AgentProcessManager",
    "ClaudeCodeAdapter",
    "CodexAdapter",
    "HealthStatus",
    "ImageGenAdapter",
    "NanobotAdapter",
    "ProcessHandle",
    "default_agent_adapters",
]
