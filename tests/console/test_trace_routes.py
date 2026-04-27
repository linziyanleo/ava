from __future__ import annotations

from types import SimpleNamespace

from fastapi.testclient import TestClient

from ava.console.app import create_console_app, get_services
from ava.console.mock_bundle_runtime import MOCK_TESTER_PASSWORD_FILE


def _config() -> SimpleNamespace:
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


def test_mock_tester_can_read_mock_trace_routes(tmp_path, monkeypatch):
    monkeypatch.setattr("ava.console.app.prepare_console_ui_dist", lambda: None)
    nanobot_dir = tmp_path / "nanobot-home"
    workspace = tmp_path / "workspace"
    nanobot_dir.mkdir()
    workspace.mkdir()

    app = create_console_app(
        nanobot_dir=nanobot_dir,
        workspace=workspace,
        agent_loop=SimpleNamespace(lifecycle_manager=None),
        config=_config(),
        token_stats_collector=None,
        db=None,
    )
    services = get_services()
    assert services.mock is not None
    assert services.mock.trace_spans is not None
    services.mock.trace_spans.start_span("trace-route", "root", "", "invoke_agent", "invoke_agent")
    services.mock.trace_spans.end_span("trace-route", "root")

    client = TestClient(app)
    password = (nanobot_dir / "console" / "local-secrets" / MOCK_TESTER_PASSWORD_FILE).read_text("utf-8").strip()
    login = client.post("/api/auth/login", json={"username": "mock_tester", "password": password})
    assert login.status_code == 200

    trace = client.get("/api/stats/traces/trace-route")
    assert trace.status_code == 200
    assert trace.json()["spans"][0]["span_id"] == "root"

    traces = client.get("/api/stats/traces")
    assert traces.status_code == 200
    assert any(item["trace_id"] == "trace-route" for item in traces.json()["traces"])
