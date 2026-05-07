from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest

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
        "ava.console.services.agent_registry_service.shutil.which",
        lambda name: f"/usr/local/bin/{name}" if name in {"codex", "claude"} else None,
    )

    def fake_run(args, **_kwargs):
        binary = Path(args[0]).name
        return SimpleNamespace(stdout=f"{binary} 1.2.3\n", stderr="")

    monkeypatch.setattr("ava.console.services.agent_registry_service.subprocess.run", fake_run)

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


def test_agent_registry_does_not_treat_runtime_workspace_as_project_root(tmp_path, monkeypatch):
    checkout = tmp_path / "nanobot"
    calls: list[Path | None] = []

    def fake_resolve_nanobot_root(*, project_root=None, explicit_root=None):
        calls.append(project_root)
        assert explicit_root is None
        return checkout

    monkeypatch.setattr(
        "ava.console.services.agent_registry_service.resolve_nanobot_root",
        fake_resolve_nanobot_root,
    )
    monkeypatch.setattr("ava.console.services.agent_registry_service.shutil.which", lambda _name: None)
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
    monkeypatch.setattr("ava.console.services.agent_registry_service.shutil.which", lambda _name: None)
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
    monkeypatch.setattr("ava.console.services.agent_registry_service.shutil.which", lambda _name: None)
    monkeypatch.setattr(
        "ava.console.services.agent_registry_service.resolve_nanobot_root",
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
    monkeypatch.setattr("ava.console.services.agent_registry_service.shutil.which", lambda _name: None)
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
