from __future__ import annotations

import sys
import time
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import pytest

from ava.agents.adapter import AgentRuntimeContext
from ava.agents.process_manager import AgentProcessManager
from ava.console.services.agent_registry_service import AgentRegistryService
from ava.storage.database import Database


class _FakeBgStore:
    def __init__(self) -> None:
        self.cancelled: list[str] = []

    def get_status(self, include_finished: bool = False):
        return {
            "tasks": [
                {
                    "task_id": "codex-1",
                    "task_type": "codex",
                    "status": "running",
                    "started_at": 10,
                    "prompt_preview": "fix auth",
                    "result_preview": "diff summary",
                    "timeline": [{"timestamp": 11, "event": "running", "detail": "started"}],
                },
                {"task_id": "claude-1", "task_type": "claude_code", "status": "queued"},
                {"task_id": "old-1", "task_type": "codex", "status": "succeeded"},
            ]
        }

    async def cancel(self, task_id: str) -> str:
        self.cancelled.append(task_id)
        return f"Task {task_id} cancelled."


class _DummyAdapter:
    name = "dummy"
    instance_id = "dummy:default"
    display_name = "Dummy"
    kind = "test"
    task_type = "dummy"
    artifact_type = "text"

    def matches(self, agent_name: str) -> bool:
        return agent_name in {self.name, self.instance_id}

    def build_snapshot(self, _context, *, active_tasks: int, activity: dict[str, list[dict[str, Any]]]):
        return {
            "name": self.name,
            "instance_id": self.instance_id,
            "display_name": self.display_name,
            "kind": self.kind,
            "status": "running" if active_tasks else "available",
            "installed": True,
            "path": "/tmp/dummy",
            "version": "dummy 1.0",
            "detail": "",
            "install_url": "",
            "active_tasks": active_tasks,
            "recent_events": activity["events"],
            "recent_artifacts": activity["artifacts"],
            "capabilities": {
                "supports_chat": False,
                "supports_task": True,
                "supports_cancel": active_tasks > 0,
                "supports_restart": False,
                "supports_streaming": False,
                "supports_artifacts": False,
                "max_concurrent_tasks": 1,
                "supported_artifact_types": ["text"],
            },
        }


class _LifecycleAdapter(_DummyAdapter):
    name = "managed"
    instance_id = "managed:default"
    display_name = "Managed"
    task_type = "managed"

    def __init__(self, code: str) -> None:
        self._code = code

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


def _make_nanobot_checkout(root: Path) -> Path:
    (root / "nanobot" / "cli").mkdir(parents=True)
    (root / "nanobot" / "config").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname='nanobot-ai'\n", encoding="utf-8")
    (root / "nanobot" / "__main__.py").write_text("", encoding="utf-8")
    (root / "nanobot" / "cli" / "commands.py").write_text("", encoding="utf-8")
    return root


def test_agent_registry_reports_runtime_and_cli_agents(tmp_path, monkeypatch):
    checkout = _make_nanobot_checkout(tmp_path / "nanobot")
    monkeypatch.setenv("AVA_NANOBOT_ROOT", str(checkout))
    monkeypatch.setattr(
        "ava.agents.adapter.shutil.which",
        lambda name: f"/usr/local/bin/{name}" if name in {"codex", "claude"} else None,
    )

    def fake_run(args, **_kwargs):
        binary = Path(args[0]).name
        return SimpleNamespace(stdout=f"{binary} 1.2.3\n", stderr="")

    monkeypatch.setattr("ava.agents.adapter.subprocess.run", fake_run)

    tools = SimpleNamespace(get=lambda name: object() if name == "image_gen" else None)
    service = AgentRegistryService(
        agent_loop=SimpleNamespace(tools=tools, version="nanobot-test"),
        workspace=tmp_path / "workspace",
        bg_store=_FakeBgStore(),
        media_service=None,
    )

    payload = service.list_agents()
    by_name = {agent["name"]: agent for agent in payload["agents"]}

    assert payload["summary"] == {"total": 4, "available": 4, "running": 3}
    assert by_name["nanobot"]["status"] == "running"
    assert by_name["nanobot"]["path"] == str(checkout)
    assert by_name["nanobot"]["capabilities"]["supports_restart"] is True
    assert by_name["codex"]["status"] == "running"
    assert by_name["codex"]["active_tasks"] == 1
    assert by_name["codex"]["version"] == "codex 1.2.3"
    assert by_name["codex"]["recent_events"][0]["event"] == "running"
    assert by_name["codex"]["recent_artifacts"][0]["preview"] == "diff summary"
    assert by_name["claude_code"]["status"] == "running"
    assert by_name["image_gen"]["status"] == "available"


def test_agent_registry_accepts_external_adapter(tmp_path):
    class DummyBgStore(_FakeBgStore):
        def get_status(self, include_finished: bool = False, task_type: str | None = None):
            tasks = [{"task_id": "dummy-1", "task_type": "dummy", "status": "running"}]
            return {"tasks": tasks}

    service = AgentRegistryService(
        agent_loop=None,
        workspace=tmp_path / "workspace",
        bg_store=DummyBgStore(),
        media_service=None,
        adapters=[_DummyAdapter()],
    )

    payload = service.list_agents()

    assert payload["summary"] == {"total": 1, "available": 1, "running": 1}
    assert payload["agents"][0]["name"] == "dummy"
    assert payload["agents"][0]["active_tasks"] == 1


def test_agent_registry_does_not_treat_runtime_workspace_as_project_root(tmp_path, monkeypatch):
    checkout = tmp_path / "nanobot"
    calls: list[Path | None] = []

    def fake_resolve_nanobot_root(*, project_root=None, explicit_root=None):
        calls.append(project_root)
        assert explicit_root is None
        return checkout

    monkeypatch.setattr(
        "ava.agents.nanobot.adapter.resolve_nanobot_root",
        fake_resolve_nanobot_root,
    )
    monkeypatch.setattr("ava.agents.adapter.shutil.which", lambda _name: None)
    service = AgentRegistryService(
        agent_loop=None,
        workspace=tmp_path / ".ava" / "workspace",
        bg_store=None,
        media_service=None,
    )

    by_name = {agent["name"]: agent for agent in service.list_agents()["agents"]}

    assert calls == [None]
    assert by_name["nanobot"]["path"] == str(checkout)
    assert by_name["nanobot"]["status"] == "available"


def test_agent_registry_persists_detection_to_db(tmp_path, monkeypatch):
    checkout = _make_nanobot_checkout(tmp_path / "nanobot")
    monkeypatch.setenv("AVA_NANOBOT_ROOT", str(checkout))
    monkeypatch.setattr("ava.agents.adapter.shutil.which", lambda _name: None)
    db = Database(tmp_path / "ava.db")

    service = AgentRegistryService(
        agent_loop=SimpleNamespace(tools=SimpleNamespace(get=lambda _name: None), version="nanobot-test"),
        workspace=tmp_path / "workspace",
        bg_store=None,
        media_service=None,
        db=db,
    )

    service.list_agents()
    row = db.fetchone("SELECT name, status, installed, capabilities FROM agent_registry WHERE instance_id = ?", ("nanobot:default",))

    assert row is not None
    assert row["name"] == "nanobot"
    assert row["status"] == "running"
    assert row["installed"] == 1
    assert "supports_restart" in row["capabilities"]


def test_agent_registry_reports_missing_cli(tmp_path, monkeypatch):
    def missing_nanobot_root():
        raise RuntimeError("nanobot missing")

    monkeypatch.delenv("AVA_NANOBOT_ROOT", raising=False)
    monkeypatch.setattr("ava.agents.adapter.shutil.which", lambda _name: None)
    monkeypatch.setattr(
        "ava.agents.nanobot.adapter.resolve_nanobot_root",
        missing_nanobot_root,
    )

    service = AgentRegistryService(
        agent_loop=None,
        workspace=tmp_path / "workspace",
        bg_store=None,
        media_service=None,
    )

    by_name = {agent["name"]: agent for agent in service.list_agents()["agents"]}

    assert by_name["codex"]["status"] == "unavailable"
    assert by_name["codex"]["installed"] is False
    assert "not found" in by_name["codex"]["detail"]
    assert by_name["nanobot"]["status"] == "unavailable"


@pytest.mark.asyncio
async def test_agent_registry_cancels_tasks_by_agent(tmp_path, monkeypatch):
    monkeypatch.setattr("ava.agents.adapter.shutil.which", lambda _name: None)
    bg_store = _FakeBgStore()
    service = AgentRegistryService(
        agent_loop=None,
        workspace=tmp_path / "workspace",
        bg_store=bg_store,
        media_service=None,
    )

    result = await service.cancel_agent_tasks("codex")

    assert result["cancelled"] == 1
    assert bg_store.cancelled == ["codex-1"]


@pytest.mark.asyncio
async def test_agent_registry_cancels_tasks_for_external_adapter(tmp_path):
    class DummyBgStore(_FakeBgStore):
        def get_status(self, include_finished: bool = False, task_type: str | None = None):
            return {"tasks": [{"task_id": "dummy-1", "task_type": "dummy", "status": "running"}]}

    bg_store = DummyBgStore()
    service = AgentRegistryService(
        agent_loop=None,
        workspace=tmp_path / "workspace",
        bg_store=bg_store,
        media_service=None,
        adapters=[_DummyAdapter()],
    )

    result = await service.cancel_agent_tasks("dummy")

    assert result["cancelled"] == 1
    assert bg_store.cancelled == ["dummy-1"]


def test_agent_registry_process_lifecycle_start_stop_and_events(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    events: list[dict[str, Any]] = []
    manager = AgentProcessManager(grace_seconds=0.2, on_event=events.append)
    service = AgentRegistryService(
        agent_loop=None,
        workspace=workspace,
        process_manager=manager,
        lifecycle_events=events,
        adapters=[_LifecycleAdapter("import time; time.sleep(60)")],
    )

    try:
        started = service.start_agent("managed")
        assert started["agent"] == "managed"
        assert started["agent_id"] == "managed:default"
        assert manager.healthcheck("managed:default").running is True

        payload = service.list_agents()
        agent = payload["agents"][0]
        assert agent["status"] == "running"
        assert agent["capabilities"]["supports_restart"] is True
        assert agent["recent_events"][0]["event"] == "started"

        stopped = service.stop_agent("managed")
        assert stopped["running"] is False

        payload = service.list_agents()
        assert payload["agents"][0]["recent_events"][0]["event"] == "stopped"
    finally:
        manager.stop_all()


def test_agent_registry_surfaces_exited_process_for_frontend(tmp_path):
    workspace = tmp_path / "workspace"
    workspace.mkdir()
    events: list[dict[str, Any]] = []
    manager = AgentProcessManager(grace_seconds=0.2, on_event=events.append)
    service = AgentRegistryService(
        agent_loop=None,
        workspace=workspace,
        process_manager=manager,
        lifecycle_events=events,
        adapters=[_LifecycleAdapter("import sys; sys.exit(7)")],
    )

    service.start_agent("managed")
    try:
        for _ in range(20):
            status = service.healthcheck_agent("managed")
            if not status["running"]:
                break
            time.sleep(0.05)

        assert status["running"] is False
        assert status["returncode"] == 7

        payload = service.list_agents()
        event = payload["agents"][0]["recent_events"][0]
        assert event["event"] == "exited"
        assert event["detail"] == "returncode=7"
    finally:
        manager.stop_all()
