"""Tests for AVA-26 schema endpoint + PUT 二次校验 (plan §F2-F3)."""

from __future__ import annotations

import json
from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ava.console import auth
from ava.console.routes import config_routes


def _headers(role: str = "owner") -> dict[str, str]:
    token = auth.create_access_token(
        {"sub": f"{role}_user", "role": role, "created_at": ""}
    )
    return {"Authorization": f"Bearer {token}"}


def _client(monkeypatch, *, audit_log=None) -> TestClient:
    auth.configure("x" * 48)
    audit = SimpleNamespace(log=lambda **kwargs: (audit_log or []).append(kwargs))
    config_service = SimpleNamespace(
        list_configs=lambda: [],
        read_config=lambda *_args, **_kwargs: {},
        update_config=lambda *_args, **_kwargs: {"saved": True},
        reveal_secret=lambda *_args, **_kwargs: None,
    )
    services = SimpleNamespace(audit=audit, config=config_service)
    monkeypatch.setattr(config_routes, "_FILENAME_TO_ADAPTER", config_routes._FILENAME_TO_ADAPTER)
    from ava.console import app as console_app

    monkeypatch.setattr(console_app, "get_services_for_user", lambda user=None: services)
    monkeypatch.setattr(console_app, "get_services", lambda: services)

    fastapi_app = FastAPI()
    fastapi_app.include_router(config_routes.router)
    return TestClient(fastapi_app)


def test_schema_endpoint_returns_codex_schema(monkeypatch) -> None:
    client = _client(monkeypatch)
    resp = client.get("/api/config/codex-config.toml/schema", headers=_headers())
    assert resp.status_code == 200
    body = resp.json()
    assert body["filename"] == "codex-config.toml"
    assert body["schema"]["title"] == "Codex config.toml"
    assert "model" in body["schema"]["properties"]


def test_schema_endpoint_404_for_unknown_filename(monkeypatch) -> None:
    client = _client(monkeypatch)
    resp = client.get("/api/config/cron%2Fjobs.json/schema", headers=_headers())
    # cron/jobs.json has no adapter ⇒ 404 schema_unavailable
    assert resp.status_code == 404
    body = resp.json()
    assert body["detail"]["code"] == "schema_unavailable"


def test_schema_endpoint_returns_all_four_adapter_schemas(monkeypatch) -> None:
    client = _client(monkeypatch)
    cases = [
        ("codex-config.toml", "Codex config.toml"),
        ("claude-code-settings.json", "Claude Code settings.json"),
        ("image-gen-config.json", "Image Gen config.json"),
        ("nanobot-config.json", "Nanobot config.json"),
    ]
    for filename, expected_title in cases:
        resp = client.get(f"/api/config/{filename}/schema", headers=_headers())
        assert resp.status_code == 200, filename
        assert resp.json()["schema"]["title"] == expected_title


def test_put_with_invalid_codex_config_returns_422_with_field_path(monkeypatch) -> None:
    client = _client(monkeypatch)
    bad_content = (
        '# bad approval policy\n'
        'model = "gpt-5"\n'
        'approval_policy = "definitely-not-an-enum"\n'
    )
    resp = client.put(
        "/api/config/codex-config.toml",
        json={"content": bad_content, "mtime": 0},
        headers=_headers(),
    )
    assert resp.status_code == 422
    body = resp.json()
    assert body["detail"]["code"] == "config_invalid"
    rows = body["detail"]["errors"]
    paths = {row["path"] for row in rows}
    assert any("approval_policy" in p for p in paths)


def test_put_with_invalid_json_syntax_returns_422_at_root(monkeypatch) -> None:
    client = _client(monkeypatch)
    resp = client.put(
        "/api/config/image-gen-config.json",
        json={"content": "{ this is not json", "mtime": 0},
        headers=_headers(),
    )
    assert resp.status_code == 422
    rows = resp.json()["detail"]["errors"]
    assert rows[0]["path"] == "/"
    assert "JSON parse error" in rows[0]["message"]


def test_put_with_valid_codex_config_passes(monkeypatch) -> None:
    client = _client(monkeypatch)
    good_content = 'model = "gpt-5"\napproval_policy = "never"\n'
    resp = client.put(
        "/api/config/codex-config.toml",
        json={"content": good_content, "mtime": 0},
        headers=_headers(),
    )
    assert resp.status_code == 200
    assert resp.json() == {"saved": True}


def test_put_for_unschemaed_filename_passes_through(monkeypatch) -> None:
    """Files without an adapter schema (e.g. cron/jobs.json) skip validation
    so schema rollout doesn't break unrelated config paths."""
    client = _client(monkeypatch)
    resp = client.put(
        "/api/config/cron%2Fjobs.json",
        json={"content": json.dumps([]), "mtime": 0},
        headers=_headers(),
    )
    assert resp.status_code == 200
