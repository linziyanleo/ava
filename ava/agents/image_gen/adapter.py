"""Image generation adapter."""

from __future__ import annotations

from pathlib import Path
from typing import Any

from ava.agents.adapter import AgentRuntimeContext, AgentStatus, HealthCheckSpec


class ImageGenAdapter:
    name = "image_gen"
    instance_id = "image_gen:default"
    display_name = "Image Gen"
    kind = "provider"
    task_type = "image_gen"
    artifact_type = "image"
    install_url = ""

    def matches(self, agent_name: str) -> bool:
        return agent_name in {self.name, self.instance_id}

    def get_binary_path(self, _context: AgentRuntimeContext) -> Path | None:
        return None

    def get_launch_args(self) -> list[str]:
        return []

    def get_env(self) -> dict[str, str]:
        return {}

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "Image Gen config.json",
            "type": "object",
            "required": ["model", "provider", "timeout", "background"],
            "properties": {
                "model": {
                    "title": "Model",
                    "type": "string",
                    "default": "",
                    "description": "Image generation model identifier.",
                },
                "provider": {
                    "title": "Provider",
                    "type": "string",
                    "default": "",
                    "description": "Provider used by the image generation tool.",
                },
                "timeout": {
                    "title": "Timeout",
                    "type": "integer",
                    "default": 300,
                    "minimum": 1,
                    "description": "Background image task timeout in seconds.",
                },
                "background": {
                    "title": "Background",
                    "type": "boolean",
                    "default": True,
                    "description": "Run image generation as a background task.",
                },
                "autoContinue": {
                    "title": "Auto continue",
                    "type": "boolean",
                    "default": False,
                    "description": "Continue the agent turn after image generation completes.",
                },
                "autoSend": {
                    "title": "Auto send",
                    "type": "boolean",
                    "default": False,
                    "description": "Send generated images back to the original channel automatically.",
                },
            },
            "additionalProperties": True,
        }

    def get_health_check(self) -> HealthCheckSpec:
        return {"type": "tool", "name": self.name}

    def parse_status_output(self, raw: bytes) -> AgentStatus:
        text = raw.decode("utf-8", errors="replace").strip()
        return {"detail": text}

    def build_snapshot(
        self,
        context: AgentRuntimeContext,
        *,
        active_tasks: int,
        activity: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        registered = self._get_registered_tool(context) is not None
        installed = registered or context.media_service is not None
        return {
            "name": self.name,
            "instance_id": self.instance_id,
            "display_name": self.display_name,
            "kind": self.kind,
            "status": "running" if active_tasks > 0 else ("available" if installed else "unavailable"),
            "installed": installed,
            "path": "",
            "version": "",
            "detail": "" if installed else "image_gen provider not configured",
            "install_url": self.install_url,
            "active_tasks": active_tasks,
            "recent_events": activity["events"],
            "recent_artifacts": activity["artifacts"],
            "capabilities": {
                "supports_chat": False,
                "supports_task": installed,
                "supports_cancel": active_tasks > 0,
                "supports_restart": False,
                "supports_streaming": False,
                "supports_artifacts": True,
                "max_concurrent_tasks": 1,
                "supported_artifact_types": ["image", "text", "log"],
            },
        }

    def _get_registered_tool(self, context: AgentRuntimeContext) -> Any | None:
        tools = getattr(context.agent_loop, "tools", None)
        getter = getattr(tools, "get", None)
        if not callable(getter):
            return None
        try:
            return getter(self.name)
        except Exception:
            return None
