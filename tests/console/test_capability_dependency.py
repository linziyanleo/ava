from __future__ import annotations

from datetime import timedelta

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from ava.console import auth
from ava.console.models import UserInfo


def _headers(role: str, *, kind: str = "console", capabilities: list[str] | None = None) -> dict[str, str]:
    payload = {
        "sub": f"{role}_user",
        "role": role,
        "created_at": "",
    }
    if kind == "device":
        payload.update({
            "kind": "device",
            "sub": "device:phone",
            "device_id": "phone",
            "token_id": "token",
            "capabilities": capabilities or [],
        })
    token = auth.create_access_token(payload, expires_delta=timedelta(minutes=30))
    return {"Authorization": f"Bearer {token}"}


def _client() -> TestClient:
    auth.configure("x" * 48)
    auth.set_device_token_validator(lambda _payload: True)
    app = FastAPI()

    @app.post("/api/console/direct-tasks")
    async def submit(
        user: UserInfo = Depends(
            auth.require_console_role_or_device_capability(
                console_roles=auth.EDIT_ROLES,
                device_capabilities=("operate",),
            )
        ),
    ):
        return {"user": user.username, "role": user.role}

    @app.get("/api/agents")
    async def read_agents(
        user: UserInfo = Depends(
            auth.require_console_role_or_device_capability(
                console_roles=auth.READ_ROLES,
                device_capabilities=("read",),
            )
        ),
    ):
        return {"user": user.username, "role": user.role}

    @app.post("/api/agents/nanobot/process/start")
    async def process_action(user: UserInfo = Depends(auth.require_role("owner"))):
        return {"user": user.username}

    return TestClient(app)


def test_operate_or_helper_separates_console_roles_from_device_capabilities():
    client = _client()

    assert client.post("/api/console/direct-tasks", headers=_headers("owner")).status_code == 200
    assert client.post(
        "/api/console/direct-tasks",
        headers=_headers("read_only", kind="device", capabilities=["read"]),
    ).status_code == 403
    assert client.post(
        "/api/console/direct-tasks",
        headers=_headers("read_only", kind="device", capabilities=["read", "operate"]),
    ).status_code == 200


def test_read_and_owner_only_routes_do_not_degrade():
    client = _client()

    assert client.get(
        "/api/agents",
        headers=_headers("read_only", kind="device", capabilities=[]),
    ).status_code == 403
    assert client.get(
        "/api/agents",
        headers=_headers("read_only", kind="device", capabilities=["read"]),
    ).status_code == 200
    assert client.get("/api/agents", headers=_headers("owner")).status_code == 200
    assert client.post("/api/agents/nanobot/process/start", headers=_headers("owner")).status_code == 200
    assert client.post(
        "/api/agents/nanobot/process/start",
        headers=_headers("read_only", kind="device", capabilities=["read", "operate"]),
    ).status_code == 403


def test_no_standalone_capability_dependency_is_exposed():
    assert not hasattr(auth, "require_capability")
