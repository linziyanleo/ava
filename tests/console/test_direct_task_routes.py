from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from ava.agent.bg_tasks import SubmitResult
from ava.console import auth
from ava.console.app import create_console_app
from ava.console.services.trace_context import current_trace_context
from ava.storage import Database


class _FakeBgStore:
    def __init__(self) -> None:
        self.calls: list[dict] = []

    def submit_task(self, **kwargs):
        trace_ctx = current_trace_context.get()
        if trace_ctx is not None:
            kwargs["captured_trace_id"] = trace_ctx.trace_id
            kwargs["captured_parent_span_id"] = trace_ctx.span_id
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


def _create_client(
    tmp_path: Path,
    monkeypatch,
    bg_store: _FakeBgStore,
    *,
    db: Database | None = None,
) -> TestClient:
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
        db=db,
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
    payload = response.json()
    assert payload == {
        "task_id": "direct_001",
        "status": "queued",
        "task_type": "codex",
        "origin_conversation_id": "conv_1",
        "origin_turn_seq": 2,
        "trace_id": payload["trace_id"],
    }
    assert payload["trace_id"]
    assert bg_store.calls[0]["origin_session_key"] == "console:abc123"
    assert bg_store.calls[0]["origin_conversation_id"] == "conv_1"


def test_submit_direct_task_route_returns_trace_id_when_tracing_is_available(tmp_path, monkeypatch):
    bg_store = _FakeBgStore()
    db = Database(tmp_path / "console.sqlite3")
    client = _create_client(tmp_path, monkeypatch, bg_store, db=db)

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
    body = response.json()
    assert body["trace_id"]
    assert body["task_id"] == "direct_001"
    assert bg_store.calls[0]["captured_trace_id"] == body["trace_id"]
    assert bg_store.calls[0]["captured_parent_span_id"]

    row = db.fetchone(
        """SELECT trace_id, span_id, operation_name, status, session_key,
                  conversation_id, turn_seq
           FROM trace_spans
           WHERE trace_id = ?""",
        (body["trace_id"],),
    )
    assert row["span_id"] == bg_store.calls[0]["captured_parent_span_id"]
    assert row["operation_name"] == "console.direct_task.submit"
    assert row["status"] == "ok"
    assert row["session_key"] == "console:abc123"
    assert row["conversation_id"] == "conv_1"
    assert row["turn_seq"] == 2


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


def test_submit_image_gen_route_rejects_arbitrary_reference_path(tmp_path, monkeypatch):
    bg_store = _FakeBgStore()
    client = _create_client(tmp_path, monkeypatch, bg_store)
    secret = tmp_path / "secret.png"
    secret.write_bytes(b"png")

    response = client.post(
        "/api/console/direct-tasks",
        headers=_headers("editor"),
        json={
            "task_type": "image_gen",
            "prompt": "use this",
            "session_key": "console:abc123",
            "params": {"reference_image": str(secret)},
        },
    )

    assert response.status_code == 400
    assert "previously uploaded image" in response.json()["detail"]
    assert bg_store.calls == []


def test_submit_image_gen_route_accepts_uploaded_reference_path(tmp_path, monkeypatch):
    calls: list[dict] = []

    class FakeImageGenTool:
        def __init__(self, **_kwargs):
            pass

        async def execute(self, *, prompt, reference_image=None, continue_after_completion=None):
            calls.append({
                "prompt": prompt,
                "reference_image": reference_image,
                "continue_after_completion": continue_after_completion,
            })
            return "Image generation task started (id: image_gen_route_001). Use /task or /bg-tasks to check progress."

    monkeypatch.setattr("ava.console.services.direct_task_service.ImageGenTool", FakeImageGenTool)
    bg_store = _FakeBgStore()
    client = _create_client(tmp_path, monkeypatch, bg_store)

    upload = client.post(
        "/api/chat/uploads",
        headers=_headers("editor"),
        files=[("files", ("reference.png", b"png", "image/png"))],
    )
    assert upload.status_code == 200
    upload_item = upload.json()["uploads"][0]

    response = client.post(
        "/api/console/direct-tasks",
        headers=_headers("editor"),
        json={
            "task_type": "image_gen",
            "prompt": "make it warmer",
            "session_key": "console:abc123",
            "params": {"reference_image": upload_item["path"]},
        },
    )

    assert response.status_code == 201
    assert response.json()["task_id"] == "image_gen_route_001"
    assert calls[0]["prompt"] == "make it warmer"
    assert calls[0]["reference_image"] == upload_item["media_path"]
    assert calls[0]["continue_after_completion"] is None
