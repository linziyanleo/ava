from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from ava.console import auth
from ava.console.app import create_console_app


class _FakeBgStore:
    def __init__(self) -> None:
        self.cancelled: list[str] = []

    def get_status(self, include_finished: bool = False):
        return {"tasks": [{"task_id": "codex-1", "task_type": "codex", "status": "running"}]}

    async def cancel(self, task_id: str) -> str:
        self.cancelled.append(task_id)
        return f"Task {task_id} cancelled."


def _headers(role: str = "viewer") -> dict[str, str]:
    token = auth.create_access_token({
        "sub": f"{role}_user",
        "role": role,
        "created_at": "",
    })
    return {"Authorization": f"Bearer {token}"}


def _make_nanobot_checkout(root: Path) -> Path:
    (root / "nanobot" / "cli").mkdir(parents=True)
    (root / "nanobot" / "config").mkdir(parents=True)
    (root / "pyproject.toml").write_text("[project]\nname='nanobot-ai'\n", encoding="utf-8")
    (root / "nanobot" / "__main__.py").write_text("", encoding="utf-8")
    (root / "nanobot" / "cli" / "commands.py").write_text("", encoding="utf-8")
    return root


def _build_config() -> SimpleNamespace:
    return SimpleNamespace(
        gateway=SimpleNamespace(
            port=18791,
            console=SimpleNamespace(
                port=6689,
                secret_key="x" * 48,
                token_expire_minutes=60,
                session_cookie_name="ava_console_session",
                session_cookie_secure=False,
                session_cookie_samesite="lax",
            ),
        ),
    )


def test_agent_route_lists_agents_for_viewer(tmp_path, monkeypatch):
    monkeypatch.setattr("ava.console.app.prepare_console_ui_dist", lambda: None)
    checkout = _make_nanobot_checkout(tmp_path / "nanobot")
    monkeypatch.setenv("AVA_NANOBOT_ROOT", str(checkout))
    monkeypatch.setattr(
        "ava.console.services.agent_registry_service.shutil.which",
        lambda name: f"/usr/local/bin/{name}" if name == "codex" else None,
    )
    monkeypatch.setattr(
        "ava.console.services.agent_registry_service.subprocess.run",
        lambda args, **_kwargs: SimpleNamespace(stdout=f"{Path(args[0]).name} 0.1.0\n", stderr=""),
    )

    nanobot_dir = tmp_path / "nanobot-home"
    workspace = tmp_path / "workspace"
    nanobot_dir.mkdir()
    workspace.mkdir()
    bg_store = _FakeBgStore()
    agent_loop = SimpleNamespace(
        lifecycle_manager=None,
        bg_tasks=bg_store,
        tools=SimpleNamespace(get=lambda _name: None),
        version="nanobot-test",
    )
    app = create_console_app(
        nanobot_dir=nanobot_dir,
        workspace=workspace,
        agent_loop=agent_loop,
        config=_build_config(),
        token_stats_collector=None,
        db=None,
    )

    client = TestClient(app)
    response = client.get("/api/agents", headers=_headers("viewer"))

    assert response.status_code == 200
    payload = response.json()
    by_name = {agent["name"]: agent for agent in payload["agents"]}
    assert by_name["nanobot"]["status"] == "running"
    assert by_name["codex"]["status"] == "running"
    assert by_name["claude_code"]["status"] == "unavailable"

    version_response = client.get("/api/agents/codex/version", headers=_headers("viewer"))
    assert version_response.status_code == 200
    assert version_response.json()["version"] == "codex 0.1.0"

    core_response = client.get("/api/core/version", headers=_headers("viewer"))
    assert core_response.status_code == 200
    assert core_response.json()["protocol_version"] == "agent-adapter/0.1"

    missing_response = client.get("/api/agents/missing/version", headers=_headers("viewer"))
    assert missing_response.status_code == 404

    cancel_response = client.post("/api/agents/codex/tasks/cancel", headers=_headers("editor"))
    assert cancel_response.status_code == 200
    assert cancel_response.json()["cancelled"] == 1
    assert bg_store.cancelled == ["codex-1"]

    viewer_cancel = client.post("/api/agents/codex/tasks/cancel", headers=_headers("viewer"))
    assert viewer_cancel.status_code == 403


def test_missing_api_route_returns_json_before_spa_fallback(tmp_path, monkeypatch):
    dist = tmp_path / "dist"
    dist.mkdir()
    (dist / "index.html").write_text("<!doctype html><html></html>", encoding="utf-8")
    monkeypatch.setattr("ava.console.app.prepare_console_ui_dist", lambda: dist)
    checkout = _make_nanobot_checkout(tmp_path / "nanobot")
    monkeypatch.setenv("AVA_NANOBOT_ROOT", str(checkout))

    nanobot_dir = tmp_path / "nanobot-home"
    workspace = tmp_path / "workspace"
    nanobot_dir.mkdir()
    workspace.mkdir()
    app = create_console_app(
        nanobot_dir=nanobot_dir,
        workspace=workspace,
        agent_loop=SimpleNamespace(
            lifecycle_manager=None,
            bg_tasks=None,
            tools=SimpleNamespace(get=lambda _name: None),
            version="nanobot-test",
        ),
        config=_build_config(),
        token_stats_collector=None,
        db=None,
    )

    client = TestClient(app)
    response = client.get("/api/not-a-route", headers=_headers("viewer"))

    assert response.status_code == 404
    assert response.headers["content-type"].startswith("application/json")
    assert response.json()["detail"] == "API route not found: /api/not-a-route"

    spa_response = client.get("/agents")
    assert spa_response.status_code == 200
    assert spa_response.text.startswith("<!doctype html>")
