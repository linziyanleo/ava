from __future__ import annotations

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ava.console import auth
from ava.console.routes import bg_task_routes


class _FakeBackgroundTaskStore:
    def __init__(self) -> None:
        self.history_calls: list[dict[str, object]] = []

    def query_history(self, **kwargs):
        self.history_calls.append(kwargs)
        return {
            "tasks": [],
            "total": 0,
            "page": kwargs["page"],
            "page_size": kwargs["page_size"],
        }


def _headers(role: str = "viewer") -> dict[str, str]:
    token = auth.create_access_token({
        "sub": f"{role}_user",
        "role": role,
        "created_at": "",
    })
    return {"Authorization": f"Bearer {token}"}


def test_history_route_passes_filter_params(monkeypatch):
    auth.configure("x" * 48)
    app = FastAPI()
    app.include_router(bg_task_routes.router)
    store = _FakeBackgroundTaskStore()
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
