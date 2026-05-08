"""Claude Code adapter."""

from __future__ import annotations

from ava.agents.adapter import CliAgentAdapter


class ClaudeCodeAdapter(CliAgentAdapter):
    name = "claude_code"
    instance_id = "claude_code:default"
    display_name = "Claude Code"
    task_type = "claude_code"
    command = "claude"
    install_url = "https://docs.anthropic.com/en/docs/claude-code"

    def get_config_schema(self) -> dict:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "Claude Code settings.json",
            "type": "object",
            "required": ["model"],
            "properties": {
                "model": {
                    "title": "Model",
                    "type": "string",
                    "default": "claude-sonnet-4-20250514",
                    "description": "Default Claude Code model used for direct tasks.",
                },
                "maxTurns": {
                    "title": "Max turns",
                    "type": "integer",
                    "default": 15,
                    "minimum": 1,
                    "description": "Maximum Claude Code turns before the task stops.",
                },
                "allowedTools": {
                    "title": "Allowed tools",
                    "type": "string",
                    "default": "Read,Edit,Bash,Glob,Grep",
                    "description": "Comma-separated Claude Code tool allowlist.",
                },
                "permissionMode": {
                    "title": "Permission mode",
                    "type": "string",
                    "enum": ["default", "acceptEdits", "bypassPermissions", "plan"],
                    "default": "default",
                    "description": "Claude Code permission mode for direct tasks.",
                },
            },
            "additionalProperties": True,
        }
