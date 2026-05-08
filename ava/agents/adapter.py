"""Agent adapter protocol and shared adapter helpers."""

from __future__ import annotations

import shutil
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Protocol


AgentStatus = dict[str, Any]
HealthCheckSpec = dict[str, Any]


@dataclass(frozen=True)
class AgentRuntimeContext:
    agent_loop: Any | None
    workspace: Path
    bg_store: Any | None = None
    media_service: Any | None = None


class AgentAdapter(Protocol):
    name: str
    instance_id: str
    display_name: str
    kind: str
    task_type: str
    artifact_type: str

    def matches(self, agent_name: str) -> bool: ...
    def get_binary_path(self, context: AgentRuntimeContext) -> Path | None: ...
    def get_launch_args(self) -> list[str]: ...
    def get_env(self) -> dict[str, str]: ...
    def get_config_schema(self) -> dict[str, Any]: ...
    def get_health_check(self) -> HealthCheckSpec: ...
    def parse_status_output(self, raw: bytes) -> AgentStatus: ...
    def build_snapshot(
        self,
        context: AgentRuntimeContext,
        *,
        active_tasks: int,
        activity: dict[str, list[dict[str, Any]]],
    ) -> dict[str, Any]: ...


class CliAgentAdapter:
    name = ""
    instance_id = ""
    display_name = ""
    kind = "cli"
    task_type = ""
    artifact_type = "text"
    command = ""
    install_url = ""

    def matches(self, agent_name: str) -> bool:
        return agent_name in {self.name, self.instance_id}

    def get_binary_path(self, _context: AgentRuntimeContext) -> Path | None:
        path = shutil.which(self.command)
        return Path(path) if path else None

    def get_launch_args(self) -> list[str]:
        return [self.command]

    def get_env(self) -> dict[str, str]:
        return {}

    def get_config_schema(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    def get_health_check(self) -> HealthCheckSpec:
        return {"type": "command", "args": [self.command, "--version"]}

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
        binary = self.get_binary_path(context)
        installed = binary is not None
        return {
            "name": self.name,
            "instance_id": self.instance_id,
            "display_name": self.display_name,
            "kind": self.kind,
            "status": "running" if active_tasks > 0 else ("available" if installed else "unavailable"),
            "installed": installed,
            "path": str(binary) if binary else "",
            "version": self._version(binary) if binary else "",
            "detail": "" if installed else f"{self.command} not found in PATH",
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
                "supported_artifact_types": ["text", "diff", "log", "workspace"],
            },
        }

    @staticmethod
    def _version(binary: Path | None) -> str:
        if binary is None:
            return ""
        try:
            completed = subprocess.run(
                [str(binary), "--version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
        except Exception:
            return ""
        output = (completed.stdout or completed.stderr or "").strip()
        return output.splitlines()[0] if output else ""
