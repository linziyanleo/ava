"""Nanobot adapter."""

from __future__ import annotations

import sys
from pathlib import Path
from typing import Any

from ava.adapters.nanobot.discovery import resolve_nanobot_root
from ava.agents.adapter import AgentRuntimeContext, AgentStatus, HealthCheckSpec


class NanobotAdapter:
    name = "nanobot"
    instance_id = "nanobot:default"
    display_name = "Nanobot"
    kind = "managed"
    task_type = ""
    artifact_type = "text"
    install_url = "https://github.com/HKUDS/nanobot"

    def matches(self, agent_name: str) -> bool:
        return agent_name in {self.name, self.instance_id}

    def get_binary_path(self, _context: AgentRuntimeContext) -> Path | None:
        try:
            resolve_nanobot_root()
        except RuntimeError:
            return None
        return Path(sys.executable)

    def get_launch_args(self) -> list[str]:
        return ["-m", "ava"]

    def get_env(self) -> dict[str, str]:
        try:
            return {"AVA_NANOBOT_ROOT": str(resolve_nanobot_root())}
        except RuntimeError:
            return {}

    def get_config_schema(self) -> dict[str, Any]:
        return {
            "$schema": "https://json-schema.org/draft/2020-12/schema",
            "title": "Nanobot config.json",
            "type": "object",
            "required": ["agents"],
            "properties": {
                "agents": {
                    "title": "Agents",
                    "description": "Nanobot agent defaults used by new chat turns and background tasks.",
                    "type": "object",
                    "required": ["defaults"],
                    "properties": {
                        "defaults": {
                            "title": "Defaults",
                            "description": "Default workspace, model, and runtime limits for Nanobot.",
                            "type": "object",
                            "required": ["workspace", "model"],
                            "properties": {
                                "workspace": {
                                    "title": "Workspace",
                                    "type": "string",
                                    "default": "",
                                    "description": "Default workspace path for Nanobot operations.",
                                },
                                "model": {
                                    "title": "Model",
                                    "type": "string",
                                    "default": "openai/gpt-5",
                                    "description": "Primary chat model in provider/model format.",
                                },
                                "provider": {
                                    "title": "Provider",
                                    "type": "string",
                                    "default": "auto",
                                    "description": "Provider override, or auto to infer from the model prefix.",
                                },
                                "maxTokens": {
                                    "title": "Max tokens",
                                    "type": "integer",
                                    "default": 4096,
                                    "minimum": 1,
                                    "description": "Maximum generated tokens for one model call.",
                                },
                                "temperature": {
                                    "title": "Temperature",
                                    "type": "number",
                                    "default": 0.2,
                                    "minimum": 0,
                                    "maximum": 2,
                                    "description": "Sampling temperature. Higher values are less deterministic.",
                                },
                                "maxToolIterations": {
                                    "title": "Max tool iterations",
                                    "type": "integer",
                                    "default": 10,
                                    "minimum": 1,
                                    "description": "Maximum tool-call iterations in one agent turn.",
                                },
                            },
                            "additionalProperties": True,
                        },
                    },
                    "additionalProperties": True,
                },
                "token_stats": {
                    "title": "Token statistics",
                    "description": "Token accounting controls for Nanobot requests.",
                    "type": "object",
                    "properties": {
                        "enabled": {
                            "title": "Enabled",
                            "type": "boolean",
                            "default": True,
                            "description": "Record token usage for Nanobot turns.",
                        },
                        "record_full_request_payload": {
                            "title": "Record payload",
                            "type": "boolean",
                            "default": False,
                            "description": "Persist full request payloads for debugging.",
                        },
                    },
                    "additionalProperties": True,
                },
                "gateway": {
                    "title": "Gateway",
                    "description": "Gateway host and port used by the local runtime.",
                    "type": "object",
                    "properties": {
                        "host": {
                            "title": "Host",
                            "type": "string",
                            "default": "127.0.0.1",
                            "description": "Gateway bind host.",
                        },
                        "port": {
                            "title": "Port",
                            "type": "integer",
                            "default": 18790,
                            "minimum": 1,
                            "maximum": 65535,
                            "description": "Gateway bind port.",
                        },
                    },
                    "additionalProperties": True,
                },
                "tools": {
                    "title": "Tools",
                    "description": "Tool safety switches used by Nanobot.",
                    "type": "object",
                    "properties": {
                        "restrictToWorkspace": {
                            "title": "Restrict to workspace",
                            "type": "boolean",
                            "default": True,
                            "description": "Limit tool file access to the configured workspace.",
                        },
                        "restrictConfigFile": {
                            "title": "Restrict config file",
                            "type": "boolean",
                            "default": True,
                            "description": "Prevent agents from reading or writing sensitive config files.",
                        },
                    },
                    "additionalProperties": True,
                },
            },
            "additionalProperties": True,
        }

    def get_health_check(self) -> HealthCheckSpec:
        return {"type": "agent_loop"}

    def parse_status_output(self, raw: bytes) -> AgentStatus:
        text = raw.decode("utf-8", errors="replace").strip()
        return {"version": text.splitlines()[0] if text else ""}

    def build_snapshot(
        self,
        context: AgentRuntimeContext,
        *,
        active_tasks: int,
        activity: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any]:
        path = ""
        detail = ""
        installed = False
        try:
            path = str(resolve_nanobot_root())
            installed = True
        except RuntimeError as exc:
            detail = str(exc)

        running = context.agent_loop is not None
        return {
            "name": self.name,
            "instance_id": self.instance_id,
            "display_name": self.display_name,
            "kind": self.kind,
            "status": "running" if running else ("available" if installed else "unavailable"),
            "installed": installed,
            "path": path,
            "version": self._safe_attr(context.agent_loop, "version") if running else "",
            "detail": detail,
            "install_url": self.install_url,
            "active_tasks": active_tasks,
            "recent_events": activity["events"],
            "recent_artifacts": activity["artifacts"],
            "capabilities": {
                "supports_chat": True,
                "supports_task": False,
                "supports_cancel": running,
                "supports_restart": running,
                "supports_streaming": running,
                "supports_artifacts": False,
                "max_concurrent_tasks": 1,
                "supported_artifact_types": ["text"],
            },
        }

    @staticmethod
    def _safe_attr(obj: Any, name: str) -> str:
        value = getattr(obj, name, "")
        return str(value) if value is not None else ""
