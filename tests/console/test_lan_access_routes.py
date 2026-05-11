from __future__ import annotations

from pathlib import Path
from types import SimpleNamespace

from fastapi.testclient import TestClient

from ava.console import auth
from ava.console.app import create_console_app
from ava.console.services.lan_access_service import LanAccessService, resolve_console_bind_host
from ava.storage import Database


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
                host="127.0.0.1",
                secret_key="x" * 48,
                token_expire_minutes=60,
                session_cookie_name="ava_console_session",
                session_cookie_secure=False,
                session_cookie_samesite="lax",
            ),
        ),
    )


def _build_client(tmp_path, monkeypatch) -> tuple[TestClient, Path]:
    monkeypatch.setattr("ava.console.app.prepare_console_ui_dist", lambda: None)
    checkout = _make_nanobot_checkout(tmp_path / "checkout")
    monkeypatch.setenv("AVA_NANOBOT_ROOT", str(checkout))
    nanobot_dir = tmp_path / "nanobot-home"
    workspace = tmp_path / "workspace"
    nanobot_dir.mkdir()
    workspace.mkdir()
    db = Database(nanobot_dir / "nanobot.db")
    app = create_console_app(
        nanobot_dir=nanobot_dir,
        workspace=workspace,
        agent_loop=SimpleNamespace(lifecycle_manager=None, bg_tasks=None, tools=SimpleNamespace(get=lambda _name: None)),
        config=_build_config(),
        token_stats_collector=None,
        db=db,
    )
    return TestClient(app), nanobot_dir


def test_lan_access_defaults_to_localhost_and_admin_toggle_controls_bind_host(tmp_path, monkeypatch):
    client, nanobot_dir = _build_client(tmp_path, monkeypatch)

    status_response = client.get("/api/lan-access/status", headers=_headers("viewer"))
    assert status_response.status_code == 200
    status = status_response.json()
    assert status["enabled"] is False
    assert status["bind_host"] == "127.0.0.1"
    assert status["lan_urls"] == []
    assert resolve_console_bind_host(nanobot_dir, "0.0.0.0") == "127.0.0.1"

    viewer_toggle = client.put("/api/lan-access/config", json={"enabled": True}, headers=_headers("viewer"))
    assert viewer_toggle.status_code == 403

    admin_toggle = client.put("/api/lan-access/config", json={"enabled": True}, headers=_headers("admin"))
    assert admin_toggle.status_code == 200
    enabled = admin_toggle.json()
    assert enabled["enabled"] is True
    assert enabled["bind_host"] == "0.0.0.0"
    assert resolve_console_bind_host(nanobot_dir, "127.0.0.1") == "0.0.0.0"

    disabled = client.put("/api/lan-access/config", json={"enabled": False}, headers=_headers("admin")).json()
    assert disabled["enabled"] is False
    assert disabled["bind_host"] == "127.0.0.1"


def test_lan_pairing_issues_read_only_device_token_and_revoke_invalidates_it(tmp_path, monkeypatch):
    client, _nanobot_dir = _build_client(tmp_path, monkeypatch)

    pin_disabled = client.post("/api/lan-access/pin", headers=_headers("admin"))
    assert pin_disabled.status_code == 409

    client.put("/api/lan-access/config", json={"enabled": True}, headers=_headers("admin"))
    pin_response = client.post("/api/lan-access/pin", headers=_headers("admin"))
    assert pin_response.status_code == 200
    pin_payload = pin_response.json()
    assert pin_payload["pin"].isdigit()
    assert len(pin_payload["pin"]) == 6

    invalid_pair = client.post("/api/lan-access/pair", json={"pin": "000000", "device_name": "phone"})
    assert invalid_pair.status_code == 401

    pair_response = client.post(
        "/api/lan-access/pair",
        json={"pin": pin_payload["pin"], "device_name": "phone"},
        headers={"User-Agent": "mobile-test"},
    )
    assert pair_response.status_code == 200
    assert "Max-Age=2592000" in pair_response.headers["set-cookie"]
    paired = pair_response.json()
    device = paired["device"]
    assert device["role"] == "read_only"
    assert device["capabilities"] == ["read"]
    token_headers = {"Authorization": f"Bearer {paired['access_token']}"}

    me_response = client.get("/api/auth/me", headers=token_headers)
    assert me_response.status_code == 200
    assert me_response.json()["role"] == "read_only"

    write_response = client.put("/api/lan-access/config", json={"enabled": False}, headers=token_headers)
    assert write_response.status_code == 403

    audit_response = client.get("/api/audit/logs?action=lan.device_access", headers=_headers("admin"))
    assert audit_response.status_code == 200
    entries = audit_response.json()["entries"]
    assert {entry["user"] for entry in entries} == {f"device:{device['device_id']}"}
    assert "/api/auth/me" in {entry["target"] for entry in entries}

    revoke_response = client.post(f"/api/lan-access/devices/{device['device_id']}/revoke", headers=_headers("admin"))
    assert revoke_response.status_code == 200
    assert revoke_response.json()["revoked_at"]

    revoked_me = client.get("/api/auth/me", headers=token_headers)
    assert revoked_me.status_code == 401


def test_lan_access_service_pin_is_single_use(tmp_path):
    service = LanAccessService(tmp_path, console_port=6688)
    service.set_enabled(True)
    pin = service.create_pairing_pin()["pin"]
    service.pair_device(pin=pin, device_name="first")

    try:
        service.pair_device(pin=pin, device_name="second")
    except ValueError as exc:
        assert "expired" in str(exc)
    else:
        raise AssertionError("pairing PIN should be single-use")


def test_lan_access_service_updates_capabilities_renews_and_cleans_expired_devices(tmp_path):
    db = Database(tmp_path / "ava.db")
    service = LanAccessService(tmp_path, console_port=6688, db=db)
    service.set_enabled(True)
    pin = service.create_pairing_pin()["pin"]
    paired = service.pair_device(pin=pin, device_name="phone")
    device_id = paired["device"]["device_id"]

    updated = service.bump_capabilities(device_id, ["read", "operate"], actor="admin")
    assert updated["capabilities"] == ["read", "operate"]

    renewed = service.renew_device(device_id)
    assert renewed["expires_at"] >= updated["expires_at"]

    db.execute("UPDATE lan_devices SET expires_at = ? WHERE device_id = ?", ("2000-01-01T00:00:00+00:00", device_id))
    db.commit()
    row = db.fetchone("SELECT token_id FROM lan_devices WHERE device_id = ?", (device_id,))
    assert service.cleanup_expired_devices() == 1
    assert service.validate_device_token({
        "device_id": device_id,
        "token_id": row["token_id"],
    }) is False


def test_lan_access_disabled_rejects_device_tokens_without_device_migration(tmp_path):
    db = Database(tmp_path / "ava.db")
    console_dir = tmp_path / "console"
    console_dir.mkdir()
    (console_dir / "lan-access.json").write_text(
        """
        {
          "enabled": false,
          "pairing": null,
          "devices": [{
            "device_id": "phone",
            "token_id": "token",
            "name": "Phone",
            "role": "read_only",
            "capabilities": ["read"],
            "created_at": "2026-05-11T00:00:00+00:00",
            "last_seen_at": "2026-05-11T00:00:00+00:00",
            "expires_at": "2026-06-11T00:00:00+00:00"
          }]
        }
        """,
        encoding="utf-8",
    )
    service = LanAccessService(tmp_path, console_port=6688, db=db)

    assert service.validate_device_token({"device_id": "phone", "token_id": "token"}) is False
    assert db.fetchone("SELECT name FROM schema_migrations WHERE name = ?", ("lan_devices_from_json_v1",)) is None
