from __future__ import annotations

import sys
import time
from pathlib import Path
from typing import Any

from ava.agents.adapter import AgentRuntimeContext
from ava.agents.process_manager import AgentProcessManager


class _PythonAdapter:
    name = "python_agent"
    instance_id = "python_agent:default"
    display_name = "Python Agent"
    kind = "test"
    task_type = "python_agent"
    artifact_type = "text"

    def __init__(self, code: str) -> None:
        self._code = code

    def matches(self, agent_name: str) -> bool:
        return agent_name in {self.name, self.instance_id}

    def get_binary_path(self, _context: AgentRuntimeContext) -> Path | None:
        return Path(sys.executable)

    def get_launch_args(self) -> list[str]:
        return ["-c", self._code]

    def get_env(self) -> dict[str, str]:
        return {}

    def get_config_schema(self) -> dict[str, Any]:
        return {}

    def get_health_check(self) -> dict[str, Any]:
        return {"type": "process"}

    def parse_status_output(self, raw: bytes) -> dict[str, Any]:
        return {"raw": raw.decode("utf-8", errors="replace")}

    def build_snapshot(self, *_args, **_kwargs) -> dict[str, Any]:
        return {}


def _context(tmp_path: Path) -> AgentRuntimeContext:
    return AgentRuntimeContext(agent_loop=None, workspace=tmp_path)


def test_start_healthcheck_stop_and_list_running(tmp_path):
    events: list[dict[str, Any]] = []
    manager = AgentProcessManager(grace_seconds=0.2, on_event=events.append)
    adapter = _PythonAdapter("import time; time.sleep(60)")

    handle = manager.start(adapter, _context(tmp_path))

    assert handle.agent_id == "python_agent:default"
    assert manager.healthcheck(handle.agent_id).running is True
    assert [item.agent_id for item in manager.list_running()] == [handle.agent_id]

    manager.stop(handle.agent_id)

    assert manager.healthcheck(handle.agent_id).running is False
    assert manager.list_running() == []
    assert [event["event"] for event in events] == ["started", "stopped"]


def test_restart_replaces_process(tmp_path):
    manager = AgentProcessManager(grace_seconds=0.2)
    adapter = _PythonAdapter("import time; time.sleep(60)")

    first = manager.start(adapter, _context(tmp_path))
    second = manager.restart(first.agent_id)

    try:
        assert second.agent_id == first.agent_id
        assert second.pid != first.pid
        assert manager.healthcheck(second.agent_id).running is True
    finally:
        manager.stop_all()


def test_exited_process_is_reaped_and_emits_event(tmp_path):
    events: list[dict[str, Any]] = []
    manager = AgentProcessManager(grace_seconds=0.2, on_event=events.append)
    adapter = _PythonAdapter("import sys; sys.exit(3)")

    handle = manager.start(adapter, _context(tmp_path))
    for _ in range(20):
        status = manager.healthcheck(handle.agent_id)
        if not status.running:
            break
        time.sleep(0.05)

    assert status.running is False
    assert status.returncode == 3
    assert manager.list_running() == []
    assert [event["event"] for event in events] == ["started", "exited"]
