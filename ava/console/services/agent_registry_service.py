"""Runtime agent registry projection for the Console."""

from __future__ import annotations

import shutil
import subprocess
import json
from pathlib import Path
from typing import Any
from datetime import datetime, timezone

from ava.adapters.nanobot.discovery import resolve_nanobot_root


class AgentRegistryService:
    """Build a read-only view of supported local agents.

    This is intentionally a runtime projection, not the long-term persistent
    AgentRuntimeStore from IDEA.md. It gives the Console a stable first surface
    for installed/running state without changing process ownership yet.
    """

    def __init__(
        self,
        *,
        agent_loop: Any | None,
        workspace: Path,
        bg_store: Any | None = None,
        media_service: Any | None = None,
        db: Any | None = None,
    ) -> None:
        self._agent_loop = agent_loop
        self._workspace = Path(workspace)
        self._bg_store = bg_store
        self._media_service = media_service
        self._db = db

    def list_agents(self) -> dict[str, Any]:
        active_counts = self._active_task_counts()
        agents = [
            self._nanobot_agent(),
            self._cli_agent(
                name="claude_code",
                display_name="Claude Code",
                command="claude",
                task_type="claude_code",
                install_url="https://docs.anthropic.com/en/docs/claude-code",
                active_tasks=active_counts.get("claude_code", 0),
            ),
            self._cli_agent(
                name="codex",
                display_name="Codex",
                command="codex",
                task_type="codex",
                install_url="https://github.com/openai/codex",
                active_tasks=active_counts.get("codex", 0),
            ),
            self._image_agent(active_tasks=active_counts.get("image_gen", 0)),
        ]
        payload = {
            "agents": agents,
            "summary": {
                "total": len(agents),
                "available": sum(1 for agent in agents if agent["installed"]),
                "running": sum(1 for agent in agents if agent["status"] == "running"),
            },
        }
        self._persist_agents(agents)
        return payload

    async def cancel_agent_tasks(self, agent_name: str) -> dict[str, Any]:
        task_type = self._task_type_for_agent(agent_name)
        if not task_type:
            return {
                "agent": agent_name,
                "cancelled": 0,
                "message": f"Agent does not expose cancellable background tasks: {agent_name}",
            }

        getter = getattr(self._bg_store, "get_status", None)
        cancel = getattr(self._bg_store, "cancel", None)
        if not callable(getter) or not callable(cancel):
            return {
                "agent": agent_name,
                "cancelled": 0,
                "message": "Background task runtime unavailable",
            }

        try:
            status = getter(task_type=task_type, include_finished=False)
        except TypeError:
            status = getter(include_finished=False)
        tasks = status.get("tasks", []) if isinstance(status, dict) else []
        cancelled = 0
        for task in tasks:
            if not isinstance(task, dict):
                continue
            if str(task.get("task_type") or "") != task_type:
                continue
            if task.get("status") not in {"queued", "running"}:
                continue
            task_id = str(task.get("task_id") or "")
            if not task_id:
                continue
            result = await cancel(task_id)
            if "cancelled" in str(result).lower():
                cancelled += 1
        return {
            "agent": agent_name,
            "task_type": task_type,
            "cancelled": cancelled,
            "message": f"Cancelled {cancelled} task(s).",
        }

    def _nanobot_agent(self) -> dict[str, Any]:
        path = ""
        detail = ""
        installed = False
        try:
            path = str(resolve_nanobot_root())
            installed = True
        except RuntimeError as exc:
            detail = str(exc)

        running = self._agent_loop is not None
        return {
            "name": "nanobot",
            "instance_id": "nanobot:default",
            "display_name": "Nanobot",
            "kind": "managed",
            "status": "running" if running else ("available" if installed else "unavailable"),
            "installed": installed,
            "path": path,
            "version": self._safe_attr(self._agent_loop, "version") if running else "",
            "detail": detail,
            "install_url": "https://github.com/HKUDS/nanobot",
            "active_tasks": 0,
            "recent_events": [],
            "recent_artifacts": [],
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

    def _cli_agent(
        self,
        *,
        name: str,
        display_name: str,
        command: str,
        task_type: str,
        install_url: str,
        active_tasks: int,
    ) -> dict[str, Any]:
        path = shutil.which(command) or ""
        installed = bool(path)
        activity = self._recent_activity(task_type)
        return {
            "name": name,
            "instance_id": f"{name}:default",
            "display_name": display_name,
            "kind": "cli",
            "status": "running" if active_tasks > 0 else ("available" if installed else "unavailable"),
            "installed": installed,
            "path": path,
            "version": self._version(path) if path else "",
            "detail": "" if installed else f"{command} not found in PATH",
            "install_url": install_url,
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

    def _image_agent(self, *, active_tasks: int) -> dict[str, Any]:
        registered = self._get_registered_tool("image_gen") is not None
        installed = registered or self._media_service is not None
        activity = self._recent_activity("image_gen")
        return {
            "name": "image_gen",
            "instance_id": "image_gen:default",
            "display_name": "Image Gen",
            "kind": "provider",
            "status": "running" if active_tasks > 0 else ("available" if installed else "unavailable"),
            "installed": installed,
            "path": "",
            "version": "",
            "detail": "" if installed else "image_gen provider not configured",
            "install_url": "",
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

    def _active_task_counts(self) -> dict[str, int]:
        getter = getattr(self._bg_store, "get_status", None)
        if not callable(getter):
            return {}
        try:
            status = getter(include_finished=False)
        except TypeError:
            status = getter()
        except Exception:
            return {}
        tasks = status.get("tasks", []) if isinstance(status, dict) else []
        counts: dict[str, int] = {}
        for task in tasks:
            if not isinstance(task, dict):
                continue
            state = str(task.get("status") or "")
            if state not in {"queued", "running"}:
                continue
            task_type = str(task.get("task_type") or "")
            counts[task_type] = counts.get(task_type, 0) + 1
        return counts

    def _recent_activity(self, task_type: str, *, limit: int = 3) -> dict[str, list[dict[str, Any]]]:
        tasks = self._tasks_for_type(task_type, limit=limit)
        events: list[dict[str, Any]] = []
        artifacts: list[dict[str, Any]] = []
        for task in tasks:
            task_id = str(task.get("task_id") or "")
            if not task_id:
                continue
            timeline = task.get("timeline") if isinstance(task.get("timeline"), list) else []
            if timeline:
                for event in timeline[-2:]:
                    if not isinstance(event, dict):
                        continue
                    events.append({
                        "task_id": task_id,
                        "timestamp": event.get("timestamp"),
                        "event": event.get("event") or task.get("status") or "",
                        "detail": event.get("detail") or "",
                    })
            else:
                events.append({
                    "task_id": task_id,
                    "timestamp": task.get("finished_at") or task.get("started_at"),
                    "event": task.get("status") or "",
                    "detail": task.get("prompt_preview") or "",
                })

            result = str(task.get("result_preview") or task.get("error_message") or "").strip()
            if result:
                artifacts.append({
                    "task_id": task_id,
                    "type": "image" if task_type == "image_gen" else "text",
                    "preview": result[:240],
                })

        events.sort(key=lambda item: float(item.get("timestamp") or 0), reverse=True)
        return {
            "events": events[:limit],
            "artifacts": artifacts[:limit],
        }

    def _tasks_for_type(self, task_type: str, *, limit: int) -> list[dict[str, Any]]:
        tasks: list[dict[str, Any]] = []
        getter = getattr(self._bg_store, "get_status", None)
        if callable(getter):
            try:
                status = getter(task_type=task_type, include_finished=True)
            except TypeError:
                status = getter(include_finished=True)
            except Exception:
                status = {}
            for task in status.get("tasks", []) if isinstance(status, dict) else []:
                if isinstance(task, dict) and str(task.get("task_type") or "") == task_type:
                    tasks.append(task)

        if len(tasks) < limit:
            history = getattr(self._bg_store, "query_history", None)
            if callable(history):
                try:
                    payload = history(task_type=task_type, page=1, page_size=limit)
                except Exception:
                    payload = {}
                for task in payload.get("tasks", []) if isinstance(payload, dict) else []:
                    if isinstance(task, dict) and str(task.get("task_type") or "") == task_type:
                        tasks.append(task)

        seen: set[str] = set()
        unique: list[dict[str, Any]] = []
        for task in tasks:
            task_id = str(task.get("task_id") or "")
            if task_id in seen:
                continue
            seen.add(task_id)
            unique.append(task)
        unique.sort(key=lambda task: float(task.get("started_at") or task.get("finished_at") or 0), reverse=True)
        return unique[:limit]

    def _persist_agents(self, agents: list[dict[str, Any]]) -> None:
        if self._db is None:
            return
        now = datetime.now(timezone.utc).isoformat()
        rows = []
        for agent in agents:
            rows.append((
                agent["instance_id"],
                agent["name"],
                agent["kind"],
                agent["display_name"],
                agent["status"],
                1 if agent["installed"] else 0,
                agent["path"],
                agent["version"],
                json.dumps(agent["capabilities"], ensure_ascii=False),
                int(agent["active_tasks"]),
                agent["install_url"],
                agent["detail"],
                now,
            ))
        self._db.executemany(
            """
            INSERT INTO agent_registry (
                instance_id, name, kind, display_name, status, installed,
                path, version, capabilities, active_tasks, install_url,
                detail, last_seen
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(instance_id) DO UPDATE SET
                name=excluded.name,
                kind=excluded.kind,
                display_name=excluded.display_name,
                status=excluded.status,
                installed=excluded.installed,
                path=excluded.path,
                version=excluded.version,
                capabilities=excluded.capabilities,
                active_tasks=excluded.active_tasks,
                install_url=excluded.install_url,
                detail=excluded.detail,
                last_seen=excluded.last_seen
            """,
            rows,
        )
        self._db.commit()

    def _get_registered_tool(self, name: str) -> Any | None:
        tools = getattr(self._agent_loop, "tools", None)
        getter = getattr(tools, "get", None)
        if not callable(getter):
            return None
        try:
            return getter(name)
        except Exception:
            return None

    @staticmethod
    def _version(binary: str) -> str:
        try:
            completed = subprocess.run(
                [binary, "--version"],
                check=False,
                capture_output=True,
                text=True,
                timeout=2,
            )
        except Exception:
            return ""
        output = (completed.stdout or completed.stderr or "").strip()
        return output.splitlines()[0] if output else ""

    @staticmethod
    def _safe_attr(obj: Any, name: str) -> str:
        value = getattr(obj, name, "")
        return str(value) if value is not None else ""

    @staticmethod
    def _task_type_for_agent(agent_name: str) -> str:
        return {
            "codex": "codex",
            "codex:default": "codex",
            "claude_code": "claude_code",
            "claude_code:default": "claude_code",
            "image_gen": "image_gen",
            "image_gen:default": "image_gen",
        }.get(agent_name, "")
