"""Codex adapter."""

from __future__ import annotations

from ava.agents.adapter import CliAgentAdapter


class CodexAdapter(CliAgentAdapter):
    name = "codex"
    instance_id = "codex:default"
    display_name = "Codex"
    task_type = "codex"
    command = "codex"
    install_url = "https://github.com/openai/codex"

    def get_config_schema(self) -> dict:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "Codex config.toml",
            "type": "object",
            "required": ["model"],
            "properties": {
                "model": {
                    "title": "Model",
                    "type": "string",
                    "default": "",
                    "description": "Default Codex model used for direct tasks.",
                },
                "api_base": {
                    "title": "API base",
                    "type": "string",
                    "default": "",
                    "description": "Optional API base URL for Codex-compatible gateways.",
                },
                "approval_policy": {
                    "title": "Approval policy",
                    "type": "string",
                    "enum": ["never", "on-request", "on-failure", "untrusted"],
                    "default": "never",
                    "description": "Codex approval policy for tool execution.",
                },
                "sandbox_mode": {
                    "title": "Sandbox mode",
                    "type": "string",
                    "enum": ["read-only", "workspace-write", "danger-full-access"],
                    "default": "workspace-write",
                    "description": "Filesystem sandbox mode for Codex tasks.",
                },
            },
            "additionalProperties": True,
        }
