from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from ava.console import auth
from ava.console.app import create_console_app


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


def _create_client(tmp_path, monkeypatch) -> tuple[TestClient, Path]:
    monkeypatch.setattr("ava.console.app.prepare_console_ui_dist", lambda: None)

    nanobot_dir = tmp_path / "nanobot-home"
    workspace = tmp_path / "workspace"
    nanobot_dir.mkdir()
    workspace.mkdir()
    (nanobot_dir / "config.json").write_text(
        json.dumps({
            "tools": {
                "mcpServers": {
                    "playwright_cdp": {
                        "command": "/bin/echo",
                        "env": {"PLAYWRIGHT_MCP_EXTENSION_TOKEN": "secret-token"},
                        "headers": {"Authorization": "Bearer secret"},
                        "enabledTools": ["browser_navigate", "browser_snapshot"],
                        "toolTimeout": 60,
                    }
                }
            }
        }),
        encoding="utf-8",
    )
    agent_loop = SimpleNamespace(
        lifecycle_manager=None,
        _mcp_connected=True,
        _mcp_connecting=False,
        _mcp_stacks={"playwright_cdp": object()},
        tools=SimpleNamespace(
            get_definitions=lambda: [
                {"function": {"name": "mcp_playwright_cdp_browser_navigate"}},
                {"name": "mcp_playwright_cdp_browser_snapshot"},
            ]
        ),
    )
    app = create_console_app(
        nanobot_dir=nanobot_dir,
        workspace=workspace,
        agent_loop=agent_loop,
        config=_build_config(),
        token_stats_collector=None,
        db=None,
    )
    return TestClient(app), nanobot_dir


def _headers(role: str) -> dict[str, str]:
    token = auth.create_access_token({
        "sub": f"{role}_user",
        "role": role,
        "created_at": "",
    })
    return {"Authorization": f"Bearer {token}"}


def test_mcp_status_route_redacts_config_for_viewer(tmp_path, monkeypatch):
    client, _ = _create_client(tmp_path, monkeypatch)

    response = client.get("/api/skills/mcp/status", headers=_headers("viewer"))

    assert response.status_code == 200
    payload = response.json()
    server = payload["servers"][0]
    assert server["name"] == "playwright_cdp"
    assert server["status"] == "connected"
    assert server["redacted"] == ["env", "headers"]
    assert server["config_redacted"]["env"] == {"PLAYWRIGHT_MCP_EXTENSION_TOKEN": "****"}
    assert server["config_redacted"]["headers"] == {"Authorization": "****"}
    assert "secret-token" not in response.text


def test_mcp_test_route_is_editor_plus(tmp_path, monkeypatch):
    client, _ = _create_client(tmp_path, monkeypatch)

    async def fake_test(self, name: str):
        return {
            "ok": True,
            "name": name,
            "status": "connected",
            "raw_tools": ["browser_snapshot"],
            "wrapped_tools": [f"mcp_{name}_browser_snapshot"],
            "error": None,
        }

    monkeypatch.setattr("ava.console.services.skills_service.SkillsService.test_mcp_server", fake_test)

    viewer_response = client.post(
        "/api/skills/mcp/test",
        json={"name": "playwright_cdp"},
        headers=_headers("viewer"),
    )
    assert viewer_response.status_code == 403

    editor_response = client.post(
        "/api/skills/mcp/test",
        json={"name": "playwright_cdp"},
        headers=_headers("editor"),
    )
    assert editor_response.status_code == 200
    assert editor_response.json()["wrapped_tools"] == ["mcp_playwright_cdp_browser_snapshot"]


def test_mcp_reconnect_route_is_admin_and_returns_501_when_unsupported(tmp_path, monkeypatch):
    client, _ = _create_client(tmp_path, monkeypatch)

    editor_response = client.post(
        "/api/skills/mcp/reconnect",
        json={},
        headers=_headers("editor"),
    )
    assert editor_response.status_code == 403

    admin_response = client.post(
        "/api/skills/mcp/reconnect",
        json={},
        headers=_headers("admin"),
    )
    assert admin_response.status_code == 501
    assert admin_response.json()["scope"] == "all"
    assert admin_response.json()["status"] == "unsupported"
