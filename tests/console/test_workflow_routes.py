from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ava.agent.workflow_store import ArtifactStore, WorkflowStore
from ava.console import auth
from ava.console.routes import workflow_routes
from ava.storage import Database


def _headers(role: str = "viewer") -> dict[str, str]:
    token = auth.create_access_token({
        "sub": f"{role}_user",
        "role": role,
        "created_at": "",
    })
    return {"Authorization": f"Bearer {token}"}


def _client(tmp_path, monkeypatch) -> tuple[TestClient, WorkflowStore, ArtifactStore]:
    auth.configure("x" * 48)
    db = Database(tmp_path / "workflow-routes.sqlite3")
    workflow_store = WorkflowStore(db)
    artifact_store = ArtifactStore(db)
    services = SimpleNamespace(workflow_store=workflow_store, artifact_store=artifact_store, mock=None)
    monkeypatch.setattr(workflow_routes, "get_services_for_user", lambda user=None: services)
    app = FastAPI()
    app.include_router(workflow_routes.router)
    return TestClient(app), workflow_store, artifact_store


def test_workflow_routes_list_chain_detail_and_artifacts(tmp_path, monkeypatch):
    client, workflows, artifacts = _client(tmp_path, monkeypatch)
    workflows.register_chain(chain_id="chain-1", trace_id="trace-1", title="Skill run")
    workflows.upsert_node(chain_id="chain-1", task_id="task-a", status="succeeded")
    artifacts.record_artifact(
        artifact_id="artifact-1",
        task_id="task-a",
        chain_id="chain-1",
        trace_id="trace-1",
        artifact_type="json",
        uri="artifact://task-a/result.json",
        preview="result",
    )

    listed = client.get("/api/workflows", params={"trace_id": "trace-1"}, headers=_headers("read_only"))
    detail = client.get("/api/workflows/chain-1", headers=_headers())
    artifact_list = client.get("/api/artifacts", params={"chain_id": "chain-1"}, headers=_headers())

    assert listed.status_code == 200
    assert listed.json()["chains"][0]["chain_id"] == "chain-1"
    assert detail.status_code == 200
    assert detail.json()["nodes"][0]["task_id"] == "task-a"
    assert detail.json()["artifacts"][0]["artifact_id"] == "artifact-1"
    assert artifact_list.json()["artifacts"][0]["uri"] == "artifact://task-a/result.json"


def test_workflow_routes_require_edit_role_for_mutation(tmp_path, monkeypatch):
    client, _, _ = _client(tmp_path, monkeypatch)

    viewer = client.post(
        "/api/workflows",
        json={"chain_id": "chain-2"},
        headers=_headers("viewer"),
    )
    editor = client.post(
        "/api/workflows",
        json={"chain_id": "chain-2", "title": "Editable"},
        headers=_headers("editor"),
    )

    assert viewer.status_code == 403
    assert editor.status_code == 200
    assert editor.json()["chain_id"] == "chain-2"


def test_workflow_node_route_advances_linear_chain(tmp_path, monkeypatch):
    client, workflows, _ = _client(tmp_path, monkeypatch)
    workflows.register_chain(chain_id="chain-3")
    workflows.upsert_node(chain_id="chain-3", task_id="task-a", status="succeeded")

    response = client.post(
        "/api/workflows/chain-3/nodes",
        json={
            "task_id": "task-b",
            "status": "awaiting_deps",
            "parent_task_ids": ["task-a"],
        },
        headers=_headers("editor"),
    )

    assert response.status_code == 200
    assert workflows.get_node("task-b").status == "queued"


def test_workflow_routes_cancel_and_retry_chain(tmp_path, monkeypatch):
    client, workflows, _ = _client(tmp_path, monkeypatch)
    workflows.register_chain(chain_id="chain-4", trace_id="trace-4", title="Retryable")
    workflows.upsert_node(chain_id="chain-4", task_id="task-a", status="succeeded", position=0)
    workflows.upsert_node(
        chain_id="chain-4",
        task_id="task-b",
        status="failed",
        parent_task_ids=["task-a"],
        position=1,
    )

    cancel = client.post("/api/workflows/chain-4/cancel", headers=_headers("editor"))
    retry = client.post("/api/workflows/chain-4/retry", headers=_headers("editor"))

    assert cancel.status_code == 200
    assert cancel.json()["status"] == "cancelled"
    assert retry.status_code == 200
    retried = retry.json()
    assert retried["chain_id"] != "chain-4"
    assert retried["trace_id"] == "trace-4"
    assert retried["metadata"]["retry_of"] == "chain-4"
    assert [node["status"] for node in retried["nodes"]] == ["queued", "awaiting_deps"]


def test_workflow_websocket_pushes_chain_and_artifact_events(tmp_path, monkeypatch):
    client, workflows, artifacts = _client(tmp_path, monkeypatch)
    workflows.register_chain(chain_id="chain-ws", trace_id="trace-ws", title="Realtime")
    workflows.upsert_node(chain_id="chain-ws", task_id="task-ws", status="streaming")
    artifacts.record_artifact(
        artifact_id="artifact-ws",
        task_id="task-ws",
        chain_id="chain-ws",
        trace_id="trace-ws",
        artifact_type="image",
        uri="artifact://task-ws/image.png",
        preview="preview",
    )

    with client.websocket_connect(
        "/api/workflows/ws?chain_id=chain-ws",
        headers=_headers("viewer"),
    ) as websocket:
        payload = websocket.receive_json()

    assert payload["type"] == "workflow_events"
    assert payload["chain_event"] == {"event": "snapshot", "count": 1}
    assert payload["artifact_event"] == {"event": "snapshot", "count": 1}
    assert payload["chains"][0]["chain_id"] == "chain-ws"
    assert payload["artifacts"][0]["artifact_id"] == "artifact-ws"
