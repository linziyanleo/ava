from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from ava.agent.bg_tasks import SubmitResult
from ava.console import auth
from ava.console.app import create_console_app


class _FakeBgStore:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def submit_task(self, **kwargs):
        self.calls.append(kwargs)
        return SubmitResult(
            task_id="direct_001",
            reused=False,
            replaced_task_id=None,
            workspace_id="",
            active_in_session=[],
        )

    def get_status(self, task_id: str, include_finished: bool = True):
        return {
            "running": 1,
            "total": 1,
            "tasks": [{
                "task_id": task_id,
                "status": "queued",
            }],
        }


def _build_config() -> SimpleNamespace:
    return SimpleNamespace(
        gateway=SimpleNamespace(
            port=18790,
            console=SimpleNamespace(
                port=6688,
                secret_key="x" * 48,
                token_expire_minutes=60,
                session_cookie_name="ava_console_session",
                session_cookie_secure=False,
                session_cookie_samesite="lax",
            ),
        ),
    )


def _headers(role: str) -> dict[str, str]:
    token = auth.create_access_token({
        "sub": f"{role}_user",
        "role": role,
        "created_at": "",
    })
    return {"Authorization": f"Bearer {token}"}


def _create_client(tmp_path: Path, monkeypatch, bg_store: _FakeBgStore) -> TestClient:
    monkeypatch.setattr("ava.console.app.prepare_console_ui_dist", lambda: None)
    monkeypatch.setattr("ava.console.services.direct_task_service.shutil.which", lambda _name: "/usr/local/bin/tool")
    monkeypatch.setattr("ava.tools.codex.shutil.which", lambda _name: "/usr/local/bin/codex")

    nanobot_dir = tmp_path / "nanobot-home"
    workspace = tmp_path / "workspace"
    nanobot_dir.mkdir()
    workspace.mkdir()

    agent_loop = SimpleNamespace(
        lifecycle_manager=None,
        bg_tasks=bg_store,
        tools=SimpleNamespace(get=lambda _name: None),
    )
    app = create_console_app(
        nanobot_dir=nanobot_dir,
        workspace=workspace,
        agent_loop=agent_loop,
        config=_build_config(),
        token_stats_collector=None,
        db=None,
    )
    return TestClient(app)


def test_submit_direct_task_route_creates_background_task(tmp_path, monkeypatch):
    bg_store = _FakeBgStore()
    client = _create_client(tmp_path, monkeypatch, bg_store)

    response = client.post(
        "/api/console/direct-tasks",
        headers=_headers("editor"),
        json={
            "task_type": "codex",
            "prompt": "fix auth",
            "session_key": "console:abc123",
            "conversation_id": "conv_1",
            "turn_seq": 2,
            "project_path": str(tmp_path / "workspace"),
            "params": {"mode": "standard"},
        },
    )

    assert response.status_code == 201
    assert response.json() == {
        "task_id": "direct_001",
        "status": "queued",
        "task_type": "codex",
    }
    assert bg_store.calls[0]["origin_session_key"] == "console:abc123"
    assert bg_store.calls[0]["origin_conversation_id"] == "conv_1"


def test_submit_direct_task_route_rejects_viewer(tmp_path, monkeypatch):
    client = _create_client(tmp_path, monkeypatch, _FakeBgStore())

    response = client.post(
        "/api/console/direct-tasks",
        headers=_headers("viewer"),
        json={
            "task_type": "codex",
            "prompt": "fix auth",
            "session_key": "console:abc123",
        },
    )

    assert response.status_code == 403
