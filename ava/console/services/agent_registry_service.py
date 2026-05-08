"""Runtime agent registry projection for the Console."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Sequence
from datetime import datetime, timezone

from ava.agents import default_agent_adapters
from ava.agents.adapter import AgentAdapter, AgentRuntimeContext
from ava.agents.process_manager import AgentProcessManager, ProcessHandle


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
        process_manager: AgentProcessManager | None = None,
        lifecycle_events: list[dict[str, Any]] | None = None,
        adapters: Sequence[AgentAdapter] | None = None,
    ) -> None:
        self._agent_loop = agent_loop
        self._workspace = Path(workspace)
        self._bg_store = bg_store
        self._media_service = media_service
        self._db = db
        self._process_manager = process_manager
        self._lifecycle_events = lifecycle_events if lifecycle_events is not None else []
        self._adapters = list(adapters) if adapters is not None else default_agent_adapters()

    def list_agents(self) -> dict[str, Any]:
        active_counts = self._active_task_counts()
        context = self._adapter_context()
        managed_handles = self._managed_handles()
        agents = []
        for adapter in self._adapters:
            activity = (
                self._recent_activity(
                    adapter.task_type,
                    artifact_type=getattr(adapter, "artifact_type", "text"),
                )
                if adapter.task_type
                else {"events": [], "artifacts": []}
            )
            snapshot = adapter.build_snapshot(
                context,
                active_tasks=active_counts.get(adapter.task_type, 0) if adapter.task_type else 0,
                activity=activity,
            )
            self._apply_lifecycle_snapshot(snapshot, adapter, managed_handles)
            agents.append(snapshot)
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

    def start_agent(self, agent_name: str) -> dict[str, Any]:
        adapter = self._require_adapter(agent_name)
        manager = self._require_process_manager()
        handle = manager.start(adapter, self._adapter_context(), agent_id=adapter.instance_id)
        return self._handle_payload(adapter, handle, status="running")

    def stop_agent(self, agent_name: str, *, force: bool = False) -> dict[str, Any]:
        adapter = self._require_adapter(agent_name)
        manager = self._require_process_manager()
        manager.stop(adapter.instance_id, force=force)
        health = manager.healthcheck(adapter.instance_id)
        return {
            "agent": adapter.name,
            "agent_id": adapter.instance_id,
            "running": health.running,
            "pid": health.pid,
            "returncode": health.returncode,
            "detail": health.detail,
        }

    def restart_agent(self, agent_name: str, *, force: bool = False) -> dict[str, Any]:
        adapter = self._require_adapter(agent_name)
        manager = self._require_process_manager()
        handle = manager.restart(adapter.instance_id, force=force)
        return self._handle_payload(adapter, handle, status="running")

    def healthcheck_agent(self, agent_name: str) -> dict[str, Any]:
        adapter = self._require_adapter(agent_name)
        manager = self._require_process_manager()
        health = manager.healthcheck(adapter.instance_id)
        return {
            "agent": adapter.name,
            "agent_id": adapter.instance_id,
            "running": health.running,
            "pid": health.pid,
            "returncode": health.returncode,
            "detail": health.detail,
        }

    async def cancel_agent_tasks(self, agent_name: str) -> dict[str, Any]:
        adapter = self._find_adapter(agent_name)
        task_type = adapter.task_type if adapter else ""
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

    def _adapter_context(self) -> AgentRuntimeContext:
        return AgentRuntimeContext(
            agent_loop=self._agent_loop,
            workspace=self._workspace,
            bg_store=self._bg_store,
            media_service=self._media_service,
        )

    def _require_adapter(self, agent_name: str) -> AgentAdapter:
        adapter = self._find_adapter(agent_name)
        if adapter is None:
            raise KeyError(f"Unknown agent: {agent_name}")
        return adapter

    def _require_process_manager(self) -> AgentProcessManager:
        if self._process_manager is None:
            raise RuntimeError("Agent process manager unavailable")
        return self._process_manager

    def _find_adapter(self, agent_name: str) -> AgentAdapter | None:
        for adapter in self._adapters:
            if adapter.matches(agent_name):
                return adapter
        return None

    @staticmethod
    def _handle_payload(adapter: AgentAdapter, handle: ProcessHandle, *, status: str) -> dict[str, Any]:
        return {
            "agent": adapter.name,
            "agent_id": handle.agent_id,
            "status": status,
            "pid": handle.pid,
            "started_at": handle.started_at,
            "argv": handle.argv,
            "cwd": handle.cwd,
        }

    def _managed_handles(self) -> dict[str, ProcessHandle]:
        if self._process_manager is None:
            return {}
        return {handle.agent_id: handle for handle in self._process_manager.list_running()}

    def _apply_lifecycle_snapshot(
        self,
        snapshot: dict[str, Any],
        adapter: AgentAdapter,
        managed_handles: dict[str, ProcessHandle],
    ) -> None:
        handle = managed_handles.get(adapter.instance_id)
        if handle is not None:
            snapshot["status"] = "running"
            snapshot["installed"] = True
            if not snapshot.get("path"):
                snapshot["path"] = handle.argv[0] if handle.argv else ""
            capabilities = snapshot.get("capabilities")
            if isinstance(capabilities, dict):
                capabilities["supports_restart"] = True

        lifecycle_events = self._lifecycle_events_for(adapter)
        if lifecycle_events:
            existing = snapshot.get("recent_events")
            if not isinstance(existing, list):
                existing = []
            merged = lifecycle_events + existing
            merged.sort(key=lambda item: float(item.get("timestamp") or 0), reverse=True)
            snapshot["recent_events"] = merged[:3]

    def _lifecycle_events_for(self, adapter: AgentAdapter, limit: int = 3) -> list[dict[str, Any]]:
        agent_ids = {adapter.name, adapter.instance_id}
        events: list[dict[str, Any]] = []
        for event in reversed(self._lifecycle_events):
            agent_id = str(event.get("agent_id") or "")
            if agent_id not in agent_ids:
                continue
            returncode = event.get("returncode")
            detail = f"returncode={returncode}" if returncode is not None else ""
            events.append({
                "task_id": agent_id,
                "timestamp": event.get("timestamp"),
                "event": event.get("event") or "",
                "detail": detail,
            })
            if len(events) >= limit:
                break
        return events

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

    def _recent_activity(
        self,
        task_type: str,
        *,
        artifact_type: str = "text",
        limit: int = 3,
    ) -> dict[str, list[dict[str, Any]]]:
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
                    "type": artifact_type,
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
