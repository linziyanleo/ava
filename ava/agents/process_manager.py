"""Agent process lifecycle manager."""

from __future__ import annotations

import atexit
import os
import signal
import subprocess
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable

from ava.agents.adapter import AgentAdapter, AgentRuntimeContext


@dataclass(frozen=True)
class ProcessHandle:
    agent_id: str
    name: str
    pid: int
    started_at: float
    argv: list[str]
    cwd: str


@dataclass(frozen=True)
class HealthStatus:
    agent_id: str
    running: bool
    pid: int | None
    returncode: int | None = None
    detail: str = ""


@dataclass
class _ManagedProcess:
    adapter: AgentAdapter
    context: AgentRuntimeContext
    process: subprocess.Popen
    handle: ProcessHandle


EventCallback = Callable[[dict[str, Any]], None]


class AgentProcessManager:
    def __init__(self, *, grace_seconds: float = 3.0, on_event: EventCallback | None = None) -> None:
        self._grace_seconds = grace_seconds
        self._on_event = on_event
        self._running: dict[str, _ManagedProcess] = {}
        atexit.register(self.stop_all)

    def start(
        self,
        adapter: AgentAdapter,
        context: AgentRuntimeContext,
        *,
        agent_id: str | None = None,
    ) -> ProcessHandle:
        resolved_agent_id = agent_id or adapter.instance_id
        if resolved_agent_id in self._running:
            raise RuntimeError(f"Agent already running: {resolved_agent_id}")

        binary = adapter.get_binary_path(context)
        if binary is None:
            raise RuntimeError(f"Agent binary unavailable: {adapter.name}")

        argv = self._build_argv(binary, adapter.get_launch_args())
        env = os.environ.copy()
        env.update(adapter.get_env())
        cwd = str(context.workspace)
        process = subprocess.Popen(
            argv,
            cwd=cwd,
            env=env,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            start_new_session=True,
        )
        handle = ProcessHandle(
            agent_id=resolved_agent_id,
            name=adapter.name,
            pid=process.pid,
            started_at=time.time(),
            argv=argv,
            cwd=cwd,
        )
        self._running[resolved_agent_id] = _ManagedProcess(
            adapter=adapter,
            context=context,
            process=process,
            handle=handle,
        )
        self._emit({"event": "started", "agent_id": resolved_agent_id, "pid": process.pid})
        return handle

    def stop(self, agent_id: str, *, force: bool = False) -> None:
        managed = self._running.get(agent_id)
        if managed is None:
            return
        self._terminate(managed.process, force=force)
        self._running.pop(agent_id, None)
        self._emit({"event": "stopped", "agent_id": agent_id, "pid": managed.handle.pid})

    def restart(self, agent_id: str, *, force: bool = False) -> ProcessHandle:
        managed = self._running.get(agent_id)
        if managed is None:
            raise RuntimeError(f"Agent is not running: {agent_id}")
        adapter = managed.adapter
        context = managed.context
        self.stop(agent_id, force=force)
        return self.start(adapter, context, agent_id=agent_id)

    def healthcheck(self, agent_id: str) -> HealthStatus:
        managed = self._running.get(agent_id)
        if managed is None:
            return HealthStatus(agent_id=agent_id, running=False, pid=None, detail="not running")

        returncode = managed.process.poll()
        if returncode is None:
            return HealthStatus(agent_id=agent_id, running=True, pid=managed.process.pid)

        self._running.pop(agent_id, None)
        self._emit({
            "event": "exited",
            "agent_id": agent_id,
            "pid": managed.handle.pid,
            "returncode": returncode,
        })
        return HealthStatus(
            agent_id=agent_id,
            running=False,
            pid=managed.process.pid,
            returncode=returncode,
            detail=f"exited with code {returncode}",
        )

    def list_running(self) -> list[ProcessHandle]:
        self._reap_finished()
        return [managed.handle for managed in self._running.values()]

    def stop_all(self, *, force: bool = True) -> None:
        for agent_id in list(self._running):
            self.stop(agent_id, force=force)

    def _reap_finished(self) -> None:
        for agent_id in list(self._running):
            self.healthcheck(agent_id)

    def _terminate(self, process: subprocess.Popen, *, force: bool) -> None:
        if process.poll() is not None:
            return
        try:
            if force:
                os.killpg(process.pid, signal.SIGKILL)
            else:
                os.killpg(process.pid, signal.SIGTERM)
        except ProcessLookupError:
            return
        except PermissionError:
            if force:
                process.kill()
            else:
                process.terminate()

        try:
            process.wait(timeout=self._grace_seconds)
        except subprocess.TimeoutExpired:
            try:
                os.killpg(process.pid, signal.SIGKILL)
            except ProcessLookupError:
                return
            except PermissionError:
                process.kill()
            process.wait(timeout=self._grace_seconds)

    def _emit(self, event: dict[str, Any]) -> None:
        if self._on_event is None:
            return
        payload = dict(event)
        payload.setdefault("timestamp", time.time())
        self._on_event(payload)

    @staticmethod
    def _build_argv(binary: Path, launch_args: list[str]) -> list[str]:
        if not launch_args:
            return [str(binary)]
        first = Path(launch_args[0]).name
        if first == binary.name:
            return [str(binary), *launch_args[1:]]
        return [str(binary), *launch_args]
