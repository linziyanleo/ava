"""Kind-aware token payload validation per spec §4.2."""

from __future__ import annotations

from datetime import timedelta

import pytest
from fastapi import Depends, FastAPI, status
from fastapi.testclient import TestClient
from fastapi.websockets import WebSocketDisconnect

from ava.console import auth
from ava.console.models import UserInfo


def _token(role: str, *, kind: str | None = None, capabilities: list[str] | None = None) -> str:
    payload: dict = {
        "sub": f"{role}_user" if kind != "device" else "device:phone",
        "role": role,
        "created_at": "",
    }
    if kind == "device":
        payload.update(
            {
                "kind": "device",
                "device_id": "phone",
                "token_id": "token",
                "capabilities": capabilities or [],
            }
        )
    return auth.create_access_token(payload, expires_delta=timedelta(minutes=30))


def _build_app() -> FastAPI:
    auth.configure("x" * 48)
    auth.set_device_token_validator(lambda _payload: True)
    app = FastAPI()

    @app.get("/whoami")
    async def whoami(user: UserInfo = Depends(auth.get_current_user)):
        return {"role": user.role, "username": user.username}

    @app.websocket("/ws")
    async def ws_endpoint(websocket):
        user = await auth.get_ws_user(websocket)
        await websocket.accept()
        await websocket.send_json({"role": user.role})
        await websocket.close()

    return app


@pytest.fixture
def client() -> TestClient:
    return TestClient(_build_app())


def test_legacy_admin_console_token_rejected(client: TestClient) -> None:
    token = _token("admin")
    response = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_legacy_editor_ws_token_closed_with_1008(client: TestClient) -> None:
    token = _token("editor")
    with pytest.raises(WebSocketDisconnect) as excinfo:
        with client.websocket_connect("/ws", headers={"Authorization": f"Bearer {token}"}):
            pass
    assert excinfo.value.code == status.WS_1008_POLICY_VIOLATION


def test_device_token_with_read_only_role_passes(client: TestClient) -> None:
    token = _token("read_only", kind="device", capabilities=["read"])
    response = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["role"] == "read_only"


def test_device_token_with_tampered_owner_role_rejected(client: TestClient) -> None:
    token = _token("owner", kind="device", capabilities=["read", "operate"])
    response = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == status.HTTP_401_UNAUTHORIZED


def test_console_token_with_owner_role_passes(client: TestClient) -> None:
    token = _token("owner")
    response = client.get("/whoami", headers={"Authorization": f"Bearer {token}"})
    assert response.status_code == status.HTTP_200_OK
    assert response.json()["role"] == "owner"
