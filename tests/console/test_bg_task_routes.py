from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ava.console import auth
from ava.console.models import UserInfo
from ava.console.routes import bg_task_routes


class _FakeBackgroundTaskStore:
    def __init__(self) -> None:
        self.history_calls: list[dict[str, object]] = []
        self.status_calls: list[dict[str, object]] = []
        self.cancelled: list[str] = []

    def get_status(self, **kwargs):
        self.status_calls.append(kwargs)
        return {
            "running": 0,
            "total": 1,
            "tasks": [{
                "task_id": "codex-1",
                "trace_id": kwargs.get("trace_id") or "",
                "chain_id": kwargs.get("chain_id") or "",
            }],
        }

    def query_history(self, **kwargs):
        self.history_calls.append(kwargs)
        return {
            "tasks": [],
            "total": 0,
            "page": kwargs["page"],
            "page_size": kwargs["page_size"],
        }

    async def cancel(self, task_id: str) -> str:
        self.cancelled.append(task_id)
        return f"Task {task_id} cancelled."


def _headers(role: str = "owner", *, kind: str = "console", capabilities: list[str] | None = None) -> dict[str, str]:
    payload: dict[str, object] = {
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
    token = auth.create_access_token(payload)
    return {"Authorization": f"Bearer {token}"}


def _create_app_with_store(store: _FakeBackgroundTaskStore) -> FastAPI:
    auth.configure("x" * 48)
    auth.set_device_token_validator(lambda _payload: True)
    app = FastAPI()
    app.include_router(bg_task_routes.router)
    return app


def test_read_only_role_is_valid_console_role():
    user = UserInfo(username="mobile", role="read_only", created_at="")

    assert user.role == "read_only"


def test_history_route_passes_filter_params(monkeypatch):
    store = _FakeBackgroundTaskStore()
    app = _create_app_with_store(store)
    monkeypatch.setattr(bg_task_routes, "_get_bg_store", lambda user=None: store)

    response = TestClient(app).get(
        "/api/bg-tasks/history",
        params={
            "page": "2",
            "page_size": "15",
            "session_key": "console:s1",
            "task_type": "codex",
            "status": "succeeded",
        },
        headers=_headers(),
    )

    assert response.status_code == 200
    assert store.history_calls == [{
        "page": 2,
        "page_size": 15,
        "session_key": "console:s1",
        "task_type": "codex",
        "status": "succeeded",
    }]


def test_list_route_passes_trace_id_filter(monkeypatch):
    store = _FakeBackgroundTaskStore()
    app = _create_app_with_store(store)
    monkeypatch.setattr(bg_task_routes, "_get_bg_store", lambda user=None: store)

    response = TestClient(app).get(
        "/api/bg-tasks",
        params={"trace_id": "trace-bg", "include_finished": "true"},
        headers=_headers("read_only", kind="device", capabilities=["read"]),
    )

    assert response.status_code == 200
    assert response.json()["tasks"][0]["trace_id"] == "trace-bg"
    assert store.status_calls == [{
        "session_key": None,
        "trace_id": "trace-bg",
        "include_finished": True,
    }]


def test_list_route_passes_chain_id_filter(monkeypatch):
    store = _FakeBackgroundTaskStore()
    app = _create_app_with_store(store)
    monkeypatch.setattr(bg_task_routes, "_get_bg_store", lambda user=None: store)

    response = TestClient(app).get(
        "/api/bg-tasks",
        params={"chain_id": "chain-bg", "include_finished": "true"},
        headers=_headers("read_only", kind="device", capabilities=["read"]),
    )

    assert response.status_code == 200
    assert response.json()["tasks"][0]["chain_id"] == "chain-bg"
    assert store.status_calls == [{
        "session_key": None,
        "chain_id": "chain-bg",
        "include_finished": True,
    }]


def test_history_route_passes_trace_id_filter(monkeypatch):
    store = _FakeBackgroundTaskStore()
    app = _create_app_with_store(store)
    monkeypatch.setattr(bg_task_routes, "_get_bg_store", lambda user=None: store)

    response = TestClient(app).get(
        "/api/bg-tasks/history",
        params={"trace_id": "trace-bg"},
        headers=_headers("read_only", kind="device", capabilities=["read"]),
    )

    assert response.status_code == 200
    assert store.history_calls == [{
        "page": 1,
        "page_size": 20,
        "session_key": None,
        "task_type": None,
        "status": None,
        "trace_id": "trace-bg",
    }]


def test_history_route_passes_chain_id_filter(monkeypatch):
    store = _FakeBackgroundTaskStore()
    app = _create_app_with_store(store)
    monkeypatch.setattr(bg_task_routes, "_get_bg_store", lambda user=None: store)

    response = TestClient(app).get(
        "/api/bg-tasks/history",
        params={"chain_id": "chain-bg"},
        headers=_headers("read_only", kind="device", capabilities=["read"]),
    )

    assert response.status_code == 200
    assert store.history_calls == [{
        "page": 1,
        "page_size": 20,
        "session_key": None,
        "task_type": None,
        "status": None,
        "chain_id": "chain-bg",
    }]


def test_read_only_role_can_read_bg_tasks(monkeypatch):
    store = _FakeBackgroundTaskStore()
    app = _create_app_with_store(store)
    monkeypatch.setattr(bg_task_routes, "_get_bg_store", lambda user=None: store)

    response = TestClient(app).get("/api/bg-tasks/history", headers=_headers("read_only", kind="device", capabilities=["read"]))

    assert response.status_code == 200


def test_cancel_route_rejects_read_only_console_role(monkeypatch):
    store = _FakeBackgroundTaskStore()
    app = _create_app_with_store(store)
    monkeypatch.setattr(bg_task_routes, "_get_bg_store", lambda user=None: store)
    client = TestClient(app)

    read_only_response = client.post("/api/bg-tasks/codex-1/cancel", headers=_headers("read_only", kind="device", capabilities=["read"]))

    assert read_only_response.status_code == 403
    assert store.cancelled == []


def test_cancel_route_allows_owner(monkeypatch):
    store = _FakeBackgroundTaskStore()
    app = _create_app_with_store(store)
    monkeypatch.setattr(bg_task_routes, "_get_bg_store", lambda user=None: store)

    response = TestClient(app).post(
        "/api/bg-tasks/codex-1/cancel",
        headers=_headers("owner"),
    )

    assert response.status_code == 200
    assert response.json() == {"message": "Task codex-1 cancelled."}
    assert store.cancelled == ["codex-1"]
