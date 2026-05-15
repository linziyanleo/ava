"""POST /api/auth/desktop-session contract tests."""

from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from ava.console import auth
from ava.console.app import create_console_app
from ava.storage import Database


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


def _create_client(tmp_path: Path, monkeypatch) -> TestClient:
    monkeypatch.setattr("ava.console.app.prepare_console_ui_dist", lambda: None)
    nanobot_dir = tmp_path / "nanobot-home"
    workspace = tmp_path / "workspace"
    nanobot_dir.mkdir()
    workspace.mkdir()
    app = create_console_app(
        nanobot_dir=nanobot_dir,
        workspace=workspace,
        agent_loop=SimpleNamespace(lifecycle_manager=None),
        config=_build_config(),
        token_stats_collector=None,
        db=Database(nanobot_dir / "nanobot.db"),
    )
    return TestClient(app)


def test_desktop_session_returns_404_without_ava_desktop_env(tmp_path, monkeypatch):
    monkeypatch.delenv("AVA_DESKTOP", raising=False)
    monkeypatch.delenv("AVA_DESKTOP_TOKEN", raising=False)
    client = _create_client(tmp_path, monkeypatch)
    response = client.post(
        "/api/auth/desktop-session",
        headers={"X-Ava-Desktop-Token": "anything"},
    )
    assert response.status_code == 404


def test_desktop_session_rejects_invalid_token(tmp_path, monkeypatch):
    monkeypatch.setenv("AVA_DESKTOP", "1")
    monkeypatch.setenv("AVA_DESKTOP_TOKEN", "secret-token-value")
    client = _create_client(tmp_path, monkeypatch)
    response = client.post(
        "/api/auth/desktop-session",
        headers={"X-Ava-Desktop-Token": "wrong-token"},
    )
    assert response.status_code == 401


def test_desktop_session_rejects_missing_header(tmp_path, monkeypatch):
    monkeypatch.setenv("AVA_DESKTOP", "1")
    monkeypatch.setenv("AVA_DESKTOP_TOKEN", "secret-token-value")
    client = _create_client(tmp_path, monkeypatch)
    response = client.post("/api/auth/desktop-session")
    assert response.status_code == 401


def test_desktop_session_issues_owner_cookie_for_matching_token(tmp_path, monkeypatch):
    monkeypatch.setenv("AVA_DESKTOP", "1")
    monkeypatch.setenv("AVA_DESKTOP_TOKEN", "secret-token-value")
    client = _create_client(tmp_path, monkeypatch)

    response = client.post(
        "/api/auth/desktop-session",
        headers={"X-Ava-Desktop-Token": "secret-token-value"},
    )

    assert response.status_code == 200
    body = response.json()
    assert body["user"]["username"] == "owner"
    assert body["user"]["role"] == "owner"
    assert auth.session_cookie_name() in response.cookies

    # The issued cookie should be accepted by /api/auth/me without further auth.
    me = client.get("/api/auth/me")
    assert me.status_code == 200
    assert me.json()["role"] == "owner"


def test_desktop_session_500_when_owner_account_missing(tmp_path, monkeypatch):
    monkeypatch.setenv("AVA_DESKTOP", "1")
    monkeypatch.setenv("AVA_DESKTOP_TOKEN", "secret-token-value")
    client = _create_client(tmp_path, monkeypatch)

    # Simulate the owner row vanishing post-bootstrap.
    from ava.console import app as console_app

    services = console_app.get_services()
    services.users.delete_user("owner")

    response = client.post(
        "/api/auth/desktop-session",
        headers={"X-Ava-Desktop-Token": "secret-token-value"},
    )
    assert response.status_code == 500


@pytest.mark.parametrize("token", ["", " ", "\n"])
def test_desktop_session_rejects_blank_tokens(tmp_path, monkeypatch, token):
    monkeypatch.setenv("AVA_DESKTOP", "1")
    monkeypatch.setenv("AVA_DESKTOP_TOKEN", "secret-token-value")
    client = _create_client(tmp_path, monkeypatch)
    response = client.post(
        "/api/auth/desktop-session",
        headers={"X-Ava-Desktop-Token": token},
    )
    assert response.status_code == 401
