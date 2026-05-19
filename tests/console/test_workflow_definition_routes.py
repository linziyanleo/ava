"""Tests for AVA-48 P2c workflow definition routes (plan-step-6/8)."""

from __future__ import annotations

from types import SimpleNamespace

from fastapi import FastAPI
from fastapi.testclient import TestClient

from ava.console import auth
from ava.console.routes import workflow_definition_routes
from ava.console.services.workflow_definition_store import WorkflowDefinitionStore
from ava.storage import Database


def _headers(role: str = "owner") -> dict[str, str]:
    token = auth.create_access_token(
        {"sub": f"{role}_user", "role": role, "created_at": ""}
    )
    return {"Authorization": f"Bearer {token}"}


def _client(tmp_path, monkeypatch) -> tuple[TestClient, WorkflowDefinitionStore]:
    auth.configure("x" * 48)
    db = Database(tmp_path / "wdr.sqlite3")
    store = WorkflowDefinitionStore(db)
    services = SimpleNamespace(
        workflow_definition_store=store,
        workflow_run_service=None,
    )
    monkeypatch.setattr(
        workflow_definition_routes, "get_services_for_user", lambda user=None: services
    )
    app = FastAPI()
    app.include_router(workflow_definition_routes.router)
    return TestClient(app), store


_VALID_DEF = {
    "name": "demo",
    "version": 1,
    "steps": [
        {
            "id": "step1",
            "kind": "agent_task",
            "agent": "codex",
            "task": {"prompt_template": "do {{x}}"},
            "inputs": {"x": "$.inputs.q"},
            "outputs": ["report"],
        }
    ],
}


def test_create_then_get_definition(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    resp = client.post(
        "/api/workflow-definitions",
        json={"name": "demo", "definition": _VALID_DEF},
        headers=_headers(),
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "demo"
    assert body["current_version"] == 1
    workflow_id = body["workflow_id"]

    fetched = client.get(f"/api/workflow-definitions/{workflow_id}", headers=_headers())
    assert fetched.status_code == 200
    assert fetched.json()["current"]["version"] == 1


def test_invalid_definition_rejected(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    bad_def = dict(_VALID_DEF)
    # `conditional` is still reserved for AVA-31 / P3, so the schema must reject
    # it with the ticket name surfaced in the error body.
    bad_def["steps"] = [
        {"id": "p", "kind": "conditional", "agent": "codex", "task": {"prompt_template": "x"}}
    ]
    resp = client.post(
        "/api/workflow-definitions",
        json={"name": "broken", "definition": bad_def},
        headers=_headers(),
    )
    assert resp.status_code == 400
    assert "AVA-31" in resp.text or "reserved" in resp.text


def test_patch_with_correct_base_version(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    created = client.post(
        "/api/workflow-definitions",
        json={"name": "demo", "definition": _VALID_DEF},
        headers=_headers(),
    ).json()
    workflow_id = created["workflow_id"]

    new_def = dict(_VALID_DEF)
    new_def["description"] = "updated"
    resp = client.patch(
        f"/api/workflow-definitions/{workflow_id}",
        json={
            "base_version": 1,
            "definition": new_def,
            "change_summary": "tweak",
        },
        headers=_headers(),
    )
    assert resp.status_code == 200
    assert resp.json()["current_version"] == 2


def test_patch_with_stale_base_version_returns_409_with_diff(tmp_path, monkeypatch) -> None:
    client, store = _client(tmp_path, monkeypatch)
    created = client.post(
        "/api/workflow-definitions",
        json={"name": "demo", "definition": _VALID_DEF},
        headers=_headers(),
    ).json()
    workflow_id = created["workflow_id"]

    # Bump server version under the client's nose.
    other_def = dict(_VALID_DEF)
    other_def["description"] = "race"
    import json
    store.update_workflow(
        workflow_id=workflow_id,
        base_version=1,
        definition_json=json.dumps(other_def),
        change_summary="server side",
    )

    # Client retries with stale base_version=1 — expect 409 with full diff.
    stale = client.patch(
        f"/api/workflow-definitions/{workflow_id}",
        json={"base_version": 1, "definition": _VALID_DEF, "change_summary": "stale"},
        headers=_headers(),
    )
    assert stale.status_code == 409
    body = stale.json()
    assert body["code"] == "version_conflict"
    assert body["current_version"] == 2
    assert body["your_base_version"] == 1
    assert "current_definition_diff" in body
    assert "changed_top_level_keys" in body["current_definition_diff"]


def test_delete_marks_workflow_deleted(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    created = client.post(
        "/api/workflow-definitions",
        json={"name": "demo", "definition": _VALID_DEF},
        headers=_headers(),
    ).json()
    workflow_id = created["workflow_id"]
    resp = client.delete(f"/api/workflow-definitions/{workflow_id}", headers=_headers())
    assert resp.status_code == 200
    assert resp.json() == {"workflow_id": workflow_id, "deleted": True}
    # subsequent GET returns 404 because soft-delete hides the workflow
    assert client.get(f"/api/workflow-definitions/{workflow_id}", headers=_headers()).status_code == 404


def test_versions_history_and_restore(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    created = client.post(
        "/api/workflow-definitions",
        json={"name": "demo", "definition": _VALID_DEF},
        headers=_headers(),
    ).json()
    workflow_id = created["workflow_id"]

    new_def = dict(_VALID_DEF)
    new_def["description"] = "v2"
    client.patch(
        f"/api/workflow-definitions/{workflow_id}",
        json={"base_version": 1, "definition": new_def},
        headers=_headers(),
    )

    versions = client.get(
        f"/api/workflow-definitions/{workflow_id}/versions", headers=_headers()
    ).json()
    assert sorted([v["version"] for v in versions["versions"]]) == [1, 2]

    snapshot_v1 = client.get(
        f"/api/workflow-definitions/{workflow_id}/versions/1", headers=_headers()
    ).json()
    assert snapshot_v1["version"] == 1

    restore = client.post(
        f"/api/workflow-definitions/{workflow_id}/versions/1/restore",
        json={},
        headers=_headers(),
    )
    assert restore.status_code == 200
    assert restore.json()["version"] == 3


def test_templates_endpoint_returns_built_ins(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    resp = client.get("/api/workflow-definitions/templates", headers=_headers())
    assert resp.status_code == 200
    body = resp.json()
    ids = {t["id"] for t in body["templates"]}
    assert "codex_review_then_apply" in ids


def test_export_then_import_roundtrip(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    created = client.post(
        "/api/workflow-definitions",
        json={"name": "demo", "definition": _VALID_DEF},
        headers=_headers(),
    ).json()
    workflow_id = created["workflow_id"]

    exported = client.get(
        f"/api/workflow-definitions/{workflow_id}/export", headers=_headers()
    )
    assert exported.status_code == 200
    payload = exported.json()
    assert payload["format"] == "ava-workflow-definition"
    assert payload["definition"]["name"] == "demo"
    assert "Content-Disposition" in exported.headers

    imported = client.post(
        "/api/workflow-definitions/import",
        json={
            "format": "ava-workflow-definition",
            "format_version": 1,
            "name": "imported",
            "description": "via import",
            "definition": payload["definition"],
        },
        headers=_headers(),
    )
    assert imported.status_code == 200
    body = imported.json()
    assert body["name"] == "imported"
    assert body["current_version"] == 1
    assert body["workflow_id"] != workflow_id  # reissued (spec §F9)


def test_run_endpoint_requires_run_service(tmp_path, monkeypatch) -> None:
    client, _ = _client(tmp_path, monkeypatch)
    created = client.post(
        "/api/workflow-definitions",
        json={"name": "demo", "definition": _VALID_DEF},
        headers=_headers(),
    ).json()
    resp = client.post(
        f"/api/workflow-definitions/{created['workflow_id']}/runs",
        json={},
        headers=_headers(),
    )
    assert resp.status_code == 503
    assert "WorkflowRunService" in resp.text
