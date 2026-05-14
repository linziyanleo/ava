from __future__ import annotations

from datetime import timedelta
from types import SimpleNamespace

import pytest
from fastapi import Depends, FastAPI, Request, Response, WebSocket
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from ava.console import auth
from ava.console import middleware


def test_dynamic_cors_allows_only_exact_origins(monkeypatch):
    origins = {"https://known.trycloudflare.com"}
    monkeypatch.setattr(middleware, "origin_allowlist", lambda: set(origins))
    app = FastAPI()
    middleware.setup_cors(app)

    @app.post("/api/write")
    async def write():
        return {"ok": True}

    client = TestClient(app)

    allowed = client.options(
        "/api/write",
        headers={
            "Origin": "https://known.trycloudflare.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://known.trycloudflare.com"

    reflected = client.post("/api/write", headers={"Origin": "https://evil.example"})
    assert reflected.status_code == 403
    assert "access-control-allow-origin" not in reflected.headers

    origins.clear()
    revoked = client.options(
        "/api/write",
        headers={
            "Origin": "https://known.trycloudflare.com",
            "Access-Control-Request-Method": "POST",
        },
    )
    assert revoked.status_code == 403
    assert "access-control-allow-origin" not in revoked.headers


def test_origin_allowlist_is_exact_for_lan_https_and_tunnel(monkeypatch):
    monkeypatch.setattr(
        "ava.console.app.get_services",
        lambda: SimpleNamespace(
            lan_access=SimpleNamespace(
                allowed_lan_origins=lambda: {
                    "http://127.0.0.1:6688",
                    "http://localhost:6688",
                    "https://127.0.0.1:6688",
                    "https://localhost:6688",
                    "https://192.168.1.20:6688",
                },
            ),
            tunnel=SimpleNamespace(public_url="https://known.trycloudflare.com/"),
        ),
    )

    assert middleware.origin_allowlist() == {
        "http://127.0.0.1:6688",
        "http://localhost:6688",
        "https://127.0.0.1:6688",
        "https://localhost:6688",
        "https://192.168.1.20:6688",
        "https://known.trycloudflare.com",
    }

    app = FastAPI()
    middleware.setup_cors(app)

    @app.post("/api/write")
    async def write():
        return {"ok": True}

    client = TestClient(app)
    allowed = client.post("/api/write", headers={"Origin": "https://192.168.1.20:6688"})
    assert allowed.status_code == 200
    assert allowed.headers["access-control-allow-origin"] == "https://192.168.1.20:6688"

    for origin in [
        "https://evil.example",
        "https://192.168.1.99:9999",
        "https://192.168.1.20:9999",
    ]:
        denied = client.post("/api/write", headers={"Origin": origin})
        assert denied.status_code == 403
        assert "access-control-allow-origin" not in denied.headers


def test_explicit_origin_dependency_blocks_and_audits(monkeypatch):
    blocked: list[str] = []
    monkeypatch.setattr(middleware, "origin_allowlist", lambda: {"https://allowed.example"})
    monkeypatch.setattr(middleware, "_audit_blocked_origin", lambda _request, origin: blocked.append(origin))

    app = FastAPI()

    @app.post("/api/write")
    async def write(_origin: None = Depends(middleware.enforce_origin_allowlist)):
        return {"ok": True}

    client = TestClient(app)

    denied = client.post("/api/write", headers={"Origin": "https://evil.example"})
    assert denied.status_code == 403
    assert blocked == ["https://evil.example"]

    allowed = client.post("/api/write", headers={"Origin": "https://allowed.example"})
    assert allowed.status_code == 200


def test_ws_origin_rejected_with_policy_violation(monkeypatch):
    auth.configure("x" * 48)
    monkeypatch.setattr(middleware, "origin_allowlist", lambda: {"https://allowed.example"})
    app = FastAPI()

    @app.websocket("/ws")
    async def ws(websocket: WebSocket):
        await auth.get_ws_user(websocket)
        await websocket.accept()
        await websocket.send_json({"ok": True})

    token = auth.create_access_token(
        {"sub": "owner_user", "role": "owner", "created_at": ""},
        expires_delta=timedelta(minutes=30),
    )
    client = TestClient(app)

    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect(
            "/ws",
            headers={
                "Origin": "https://evil.example",
                "Authorization": f"Bearer {token}",
            },
        ):
            pass
    assert excinfo.value.code == 1008

    with client.websocket_connect(
        "/ws",
        headers={
            "Origin": "https://allowed.example",
            "Authorization": f"Bearer {token}",
        },
    ) as websocket:
        assert websocket.receive_json() == {"ok": True}


def test_session_cookie_secure_follows_effective_scheme(monkeypatch):
    auth.configure("x" * 48, cookie_name="test_session")
    monkeypatch.setattr("ava.console.app.get_services", lambda: SimpleNamespace(tunnel=SimpleNamespace(running=False)))
    app = FastAPI()

    @app.get("/cookie")
    async def cookie(request: Request, response: Response):
        auth.set_session_cookie(response, "token", request)
        return {"ok": True}

    http_cookie = TestClient(app, base_url="http://127.0.0.1").get("/cookie").headers["set-cookie"]
    assert "Secure" not in http_cookie

    https_cookie = TestClient(app, base_url="https://192.168.1.20").get("/cookie").headers["set-cookie"]
    assert "Secure" in https_cookie

    monkeypatch.setattr("ava.console.app.get_services", lambda: SimpleNamespace(tunnel=SimpleNamespace(running=True)))
    monkeypatch.setattr(middleware, "_client_host", lambda _request: "127.0.0.1")
    tunnel_cookie = TestClient(app, base_url="http://127.0.0.1").get(
        "/cookie",
        headers={"X-Forwarded-Proto": "https"},
    ).headers["set-cookie"]
    assert "Secure" in tunnel_cookie
