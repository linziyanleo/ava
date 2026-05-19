"""P2c workflow definition + run routes (AVA-48 plan-step-6).

New namespace `/api/workflow-definitions` and `/api/workflow-runs`. Sits beside
the legacy P1b `/api/workflows` (chains) routes; the two are intentionally
distinct schemas (see spec §0).

15 endpoints:

| Method | Path | Purpose |
|--------|------|---------|
| GET    | /api/workflow-definitions | list |
| POST   | /api/workflow-definitions | create |
| GET    | /api/workflow-definitions/{id} | detail (current version) |
| PATCH  | /api/workflow-definitions/{id} | update with `base_version` |
| DELETE | /api/workflow-definitions/{id} | soft delete |
| GET    | /api/workflow-definitions/{id}/versions | history |
| GET    | /api/workflow-definitions/{id}/versions/{v} | snapshot |
| POST   | /api/workflow-definitions/{id}/versions/{v}/restore | restore-as-new-version |
| GET    | /api/workflow-definitions/{id}/runs | run list |
| POST   | /api/workflow-definitions/{id}/runs | trigger run |
| GET    | /api/workflow-runs/{run_id} | run detail |
| GET    | /api/workflow-definitions/templates | built-in templates list |
| POST   | /api/workflow-definitions/import | import JSON |
| GET    | /api/workflow-definitions/{id}/export | export JSON |
| WS     | /api/workflow-definitions/ws | 5-event subscription |
"""

from __future__ import annotations

import asyncio
import json
import time
import uuid
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from fastapi.responses import JSONResponse
from loguru import logger

from ava.console import auth
from ava.console.app import get_services_for_user
from ava.console.models import UserInfo
from ava.console.services.workflow_definition_schema import validate_definition
from ava.console.services.workflow_definition_store import (
    WorkflowDefinitionStore,
    WorkflowRecord,
    WorkflowVersionRecord,
)
from ava.console.services.workflow_templates_loader import list_templates


router = APIRouter(prefix="/api", tags=["workflow-definitions"])


# ---------------------------------------------------------------------------
# Service accessors


def _store(user: UserInfo) -> WorkflowDefinitionStore:
    svc = get_services_for_user(user)
    store = getattr(svc, "workflow_definition_store", None)
    if store is None:
        raise HTTPException(
            status_code=503,
            detail="WorkflowDefinitionStore not initialised (P2a baseline gating)",
        )
    return store


def _run_service(user: UserInfo):
    svc = get_services_for_user(user)
    runner = getattr(svc, "workflow_run_service", None)
    if runner is None:
        raise HTTPException(
            status_code=503,
            detail=(
                "WorkflowRunService not initialised. Run dispatch is gated on the "
                "agent loop's BackgroundTaskStore being wired into Services."
            ),
        )
    return runner


# ---------------------------------------------------------------------------
# Validation helpers


def _validate_definition_or_400(payload: dict[str, Any]) -> None:
    try:
        validate_definition(payload)
    except Exception as exc:
        raise HTTPException(
            status_code=400,
            detail={
                "code": "definition_invalid",
                "message": str(exc),
            },
        ) from exc


def _summarise(wf: WorkflowRecord, version: WorkflowVersionRecord | None) -> dict[str, Any]:
    out = wf.to_dict()
    if version is not None:
        try:
            current_def = json.loads(version.definition_json)
        except (TypeError, json.JSONDecodeError):
            current_def = None
        out["current"] = {
            "version": version.version,
            "change_summary": version.change_summary,
            "created_at": version.created_at,
            "definition": current_def,
        }
    return out


# ---------------------------------------------------------------------------
# Definition CRUD


@router.get("/workflow-definitions")
async def list_definitions(
    limit: int = 100,
    include_deleted: bool = False,
    user: UserInfo = Depends(
        auth.require_console_role_or_device_capability(
            console_roles=auth.READ_ROLES, device_capabilities=("read",)
        )
    ),
):
    store = _store(user)
    workflows = store.list_workflows(include_deleted=include_deleted, limit=limit)
    return {
        "workflows": [
            _summarise(wf, store.get_current_version(wf.workflow_id)) for wf in workflows
        ]
    }


@router.post("/workflow-definitions")
async def create_definition(
    payload: dict[str, Any],
    user: UserInfo = Depends(
        auth.require_console_role_or_device_capability(
            console_roles=auth.EDIT_ROLES, device_capabilities=("operate",)
        )
    ),
):
    name = (payload.get("name") or "").strip()
    if not name:
        raise HTTPException(status_code=400, detail={"code": "name_required"})
    description = payload.get("description") or ""
    definition = payload.get("definition") or {}
    if not isinstance(definition, dict):
        raise HTTPException(
            status_code=400, detail={"code": "definition_required"}
        )
    _validate_definition_or_400(definition)

    store = _store(user)
    wf, version = store.create_workflow(
        name=name,
        description=description,
        definition_json=json.dumps(definition, ensure_ascii=False),
        change_summary=payload.get("change_summary") or "initial",
        created_by_agent=payload.get("created_by_agent") or user.username,
    )
    await _emit_definition_event(
        user,
        "workflow.updated",
        {
            "workflow_id": wf.workflow_id,
            "version": version.version,
            "change_summary": version.change_summary,
            "created_by": version.created_by_agent,
        },
    )
    return _summarise(wf, version)


@router.get("/workflow-definitions/templates")
async def list_definition_templates(
    user: UserInfo = Depends(
        auth.require_console_role_or_device_capability(
            console_roles=auth.READ_ROLES, device_capabilities=("read",)
        )
    ),
):
    return {"templates": list_templates()}


@router.get("/workflow-definitions/{workflow_id}")
async def get_definition(
    workflow_id: str,
    user: UserInfo = Depends(
        auth.require_console_role_or_device_capability(
            console_roles=auth.READ_ROLES, device_capabilities=("read",)
        )
    ),
):
    store = _store(user)
    wf = store.get_workflow(workflow_id)
    if wf is None or wf.deleted_at is not None:
        raise HTTPException(status_code=404, detail={"code": "workflow_not_found"})
    return _summarise(wf, store.get_current_version(workflow_id))


@router.patch("/workflow-definitions/{workflow_id}")
async def patch_definition(
    workflow_id: str,
    payload: dict[str, Any],
    user: UserInfo = Depends(
        auth.require_console_role_or_device_capability(
            console_roles=auth.EDIT_ROLES, device_capabilities=("operate",)
        )
    ),
):
    base_version = payload.get("base_version")
    if not isinstance(base_version, int):
        raise HTTPException(
            status_code=400, detail={"code": "base_version_required"}
        )
    definition = payload.get("definition")
    if not isinstance(definition, dict):
        raise HTTPException(
            status_code=400, detail={"code": "definition_required"}
        )
    _validate_definition_or_400(definition)

    store = _store(user)
    wf = store.get_workflow(workflow_id)
    if wf is None or wf.deleted_at is not None:
        raise HTTPException(status_code=404, detail={"code": "workflow_not_found"})

    try:
        new_version = store.update_workflow(
            workflow_id=workflow_id,
            base_version=base_version,
            definition_json=json.dumps(definition, ensure_ascii=False),
            change_summary=payload.get("change_summary") or "",
            created_by_agent=payload.get("created_by_agent") or user.username,
        )
    except ValueError as exc:
        # Stale base_version → 409 with full diff payload (spec §F7).
        current = store.get_current_version(workflow_id)
        return JSONResponse(
            status_code=409,
            content={
                "code": "version_conflict",
                "message": str(exc),
                "current_version": wf.current_version,
                "your_base_version": base_version,
                "current_definition_diff": _diff_definitions(
                    your_definition=definition,
                    current_definition=json.loads(current.definition_json) if current else None,
                ),
            },
        )

    refreshed = store.get_workflow(workflow_id)
    await _emit_definition_event(
        user,
        "workflow.updated",
        {
            "workflow_id": workflow_id,
            "version": new_version.version,
            "change_summary": new_version.change_summary,
            "created_by": new_version.created_by_agent,
        },
    )
    return _summarise(refreshed or wf, new_version)


@router.delete("/workflow-definitions/{workflow_id}")
async def delete_definition(
    workflow_id: str,
    user: UserInfo = Depends(
        auth.require_console_role_or_device_capability(
            console_roles=auth.EDIT_ROLES, device_capabilities=("operate",)
        )
    ),
):
    store = _store(user)
    wf = store.get_workflow(workflow_id)
    if wf is None or wf.deleted_at is not None:
        raise HTTPException(status_code=404, detail={"code": "workflow_not_found"})
    store.soft_delete_workflow(workflow_id)
    await _emit_definition_event(user, "workflow.deleted", {"workflow_id": workflow_id})
    return {"workflow_id": workflow_id, "deleted": True}


# ---------------------------------------------------------------------------
# Versions


@router.get("/workflow-definitions/{workflow_id}/versions")
async def list_definition_versions(
    workflow_id: str,
    user: UserInfo = Depends(
        auth.require_console_role_or_device_capability(
            console_roles=auth.READ_ROLES, device_capabilities=("read",)
        )
    ),
):
    store = _store(user)
    wf = store.get_workflow(workflow_id)
    if wf is None:
        raise HTTPException(status_code=404, detail={"code": "workflow_not_found"})
    return {"versions": [v.to_dict() for v in store.list_versions(workflow_id)]}


@router.get("/workflow-definitions/{workflow_id}/versions/{version}")
async def get_definition_version(
    workflow_id: str,
    version: int,
    user: UserInfo = Depends(
        auth.require_console_role_or_device_capability(
            console_roles=auth.READ_ROLES, device_capabilities=("read",)
        )
    ),
):
    store = _store(user)
    record = store.get_version(workflow_id, version)
    if record is None:
        raise HTTPException(status_code=404, detail={"code": "version_not_found"})
    return record.to_dict()


@router.post("/workflow-definitions/{workflow_id}/versions/{version}/restore")
async def restore_definition_version(
    workflow_id: str,
    version: int,
    payload: dict[str, Any] | None = None,
    user: UserInfo = Depends(
        auth.require_console_role_or_device_capability(
            console_roles=auth.EDIT_ROLES, device_capabilities=("operate",)
        )
    ),
):
    store = _store(user)
    wf = store.get_workflow(workflow_id)
    if wf is None or wf.deleted_at is not None:
        raise HTTPException(status_code=404, detail={"code": "workflow_not_found"})
    snapshot = store.get_version(workflow_id, version)
    if snapshot is None:
        raise HTTPException(status_code=404, detail={"code": "version_not_found"})
    new_version = store.update_workflow(
        workflow_id=workflow_id,
        base_version=wf.current_version,
        definition_json=snapshot.definition_json,
        change_summary=(payload or {}).get("change_summary")
        or f"restore from v{version}",
        created_by_agent=(payload or {}).get("created_by_agent") or user.username,
    )
    await _emit_definition_event(
        user,
        "workflow.updated",
        {
            "workflow_id": workflow_id,
            "version": new_version.version,
            "change_summary": new_version.change_summary,
            "created_by": new_version.created_by_agent,
        },
    )
    return new_version.to_dict()


# ---------------------------------------------------------------------------
# Runs


@router.get("/workflow-definitions/{workflow_id}/runs")
async def list_definition_runs(
    workflow_id: str,
    limit: int = 50,
    user: UserInfo = Depends(
        auth.require_console_role_or_device_capability(
            console_roles=auth.READ_ROLES, device_capabilities=("read",)
        )
    ),
):
    store = _store(user)
    return {"runs": [r.to_dict() for r in store.list_runs_for_workflow(workflow_id, limit=limit)]}


@router.post("/workflow-definitions/{workflow_id}/runs")
async def trigger_definition_run(
    workflow_id: str,
    payload: dict[str, Any] | None = None,
    user: UserInfo = Depends(
        auth.require_console_role_or_device_capability(
            console_roles=auth.EDIT_ROLES, device_capabilities=("operate",)
        )
    ),
):
    runner = _run_service(user)
    store = _store(user)
    wf = store.get_workflow(workflow_id)
    if wf is None or wf.deleted_at is not None:
        raise HTTPException(status_code=404, detail={"code": "workflow_not_found"})
    inputs = (payload or {}).get("inputs") or {}
    triggered_by = (payload or {}).get("triggered_by") or user.username
    error_payload: dict[str, Any] | None = None
    try:
        record = runner.start_run(
            workflow_id=workflow_id,
            version=wf.current_version,
            triggered_by=triggered_by,
            inputs=inputs,
        )
    except LookupError as exc:
        raise HTTPException(
            status_code=404,
            detail={"code": "version_not_found", "message": str(exc)},
        )
    except Exception as exc:  # StepRuntimeError or anything the runner raises
        record = None
        error_payload = {
            "code": getattr(exc, "code", "runner_error"),
            "message": str(exc),
        }
    # Resolve the canonical run record (the runner stores it before raising).
    if record is None:
        runs = store.list_runs_for_workflow(workflow_id, limit=1)
        if not runs:
            raise HTTPException(
                status_code=500,
                detail={"code": "run_not_persisted", "message": "runner failed before persistence"},
            )
        record = runs[0]
    await _emit_definition_event(
        user,
        "workflow.run.created",
        {
            "run_id": record.run_id,
            "workflow_id": workflow_id,
            "version": record.version,
            "triggered_by": record.triggered_by,
        },
    )
    # Drain the persisted step rows into per-step events. Synchronous P2a/P2b
    # runner means all steps are settled by now; the events are issued in
    # array order so consumers can render fan-out children grouped under
    # their parallel parent via ``parent_step_id``.
    for step_event in build_step_events(store, record.run_id):
        await _emit_definition_event(user, "workflow.run.step.event", step_event)
    await _emit_definition_event(
        user,
        "workflow.run.completed",
        {
            "run_id": record.run_id,
            "final_status": record.status,
            "outputs": _safe_json_loads(record.final_outputs_json),
            "duration_ms": _duration_ms(record.started_at, record.completed_at),
        },
    )
    if error_payload is not None:
        raise HTTPException(
            status_code=500,
            detail={**error_payload, "run_id": record.run_id},
        )
    return record.to_dict()


def build_step_events(
    store: WorkflowDefinitionStore, run_id: str
) -> list[dict[str, Any]]:
    """Build ``workflow.run.step.event`` payloads for every settled step row.

    AVA-25 P2b acceptance: payload carries ``parent_step_id`` so the UI can
    fold fan-out children under their ``parallel`` parent. Per spec table
    each event also carries ``run_id`` / ``step_id`` / ``event_type``.
    """
    payloads: list[dict[str, Any]] = []
    for step in store.list_steps_for_run(run_id):
        payloads.append(
            {
                "run_id": run_id,
                "step_id": step.step_id,
                "step_run_id": step.step_run_id,
                "parent_step_id": step.parent_step_id,
                "event_type": _event_type_for_status(step.status),
                "payload": {
                    "agent": step.agent,
                    "status": step.status,
                    "bg_task_id": step.bg_task_id,
                    "outputs": _safe_json_loads(step.outputs_json),
                    "error": _safe_json_loads(step.error_json),
                },
            }
        )
    return payloads


def _event_type_for_status(status: str) -> str:
    if status == "running":
        return "started"
    if status == "succeeded":
        return "succeeded"
    if status == "failed":
        return "failed"
    if status == "skipped":
        return "skipped"
    if status == "cancelled":
        return "cancelled"
    return "settled"


def _safe_json_loads(raw: str | None) -> Any:
    try:
        return json.loads(raw or "{}")
    except (TypeError, json.JSONDecodeError):
        return {}


def _duration_ms(started_at: float | None, completed_at: float | None) -> int | None:
    if started_at is None or completed_at is None:
        return None
    return int(max(0.0, completed_at - started_at) * 1000)


@router.get("/workflow-runs/{run_id}")
async def get_run_detail(
    run_id: str,
    user: UserInfo = Depends(
        auth.require_console_role_or_device_capability(
            console_roles=auth.READ_ROLES, device_capabilities=("read",)
        )
    ),
):
    store = _store(user)
    run = store.get_run(run_id)
    if run is None:
        raise HTTPException(status_code=404, detail={"code": "run_not_found"})
    steps = store.list_steps_for_run(run_id)
    return {
        "run": run.to_dict(),
        "steps": [s.to_dict() for s in steps],
    }


# ---------------------------------------------------------------------------
# Import / Export


@router.get("/workflow-definitions/{workflow_id}/export")
async def export_definition(
    workflow_id: str,
    user: UserInfo = Depends(
        auth.require_console_role_or_device_capability(
            console_roles=auth.READ_ROLES, device_capabilities=("read",)
        )
    ),
):
    store = _store(user)
    wf = store.get_workflow(workflow_id)
    if wf is None or wf.deleted_at is not None:
        raise HTTPException(status_code=404, detail={"code": "workflow_not_found"})
    current = store.get_current_version(workflow_id)
    if current is None:
        raise HTTPException(status_code=404, detail={"code": "version_not_found"})
    body = {
        "format": "ava-workflow-definition",
        "format_version": 1,
        "name": wf.name,
        "description": wf.description,
        "definition": json.loads(current.definition_json),
        "exported_at": time.time(),
    }
    headers = {
        "Content-Disposition": f'attachment; filename="{workflow_id}.json"',
    }
    return JSONResponse(content=body, headers=headers)


@router.post("/workflow-definitions/import")
async def import_definition(
    payload: dict[str, Any],
    user: UserInfo = Depends(
        auth.require_console_role_or_device_capability(
            console_roles=auth.EDIT_ROLES, device_capabilities=("operate",)
        )
    ),
):
    if payload.get("format") != "ava-workflow-definition":
        raise HTTPException(status_code=400, detail={"code": "unsupported_format"})
    definition = payload.get("definition")
    if not isinstance(definition, dict):
        raise HTTPException(status_code=400, detail={"code": "definition_required"})
    _validate_definition_or_400(definition)
    name = (payload.get("name") or "imported workflow").strip()
    description = payload.get("description") or ""

    # reissue workflow_id on import (spec §F9): never trust the inbound id.
    definition = dict(definition)
    definition.pop("workflow_id", None)
    definition["version"] = 1
    store = _store(user)
    wf, version = store.create_workflow(
        name=name,
        description=description,
        definition_json=json.dumps(definition, ensure_ascii=False),
        change_summary="imported",
        created_by_agent=user.username,
    )
    await _emit_definition_event(
        user,
        "workflow.updated",
        {
            "workflow_id": wf.workflow_id,
            "version": version.version,
            "change_summary": version.change_summary,
            "created_by": version.created_by_agent,
        },
    )
    return _summarise(wf, version)


# ---------------------------------------------------------------------------
# WebSocket — 5 event types


_WS_CLIENTS: dict[str, set[WebSocket]] = {}


async def _emit_definition_event(user: UserInfo, event_type: str, payload: dict[str, Any]) -> None:
    """Fan out a single event to all subscribed websockets."""
    bucket = _WS_CLIENTS.get(user.username, set()) | _WS_CLIENTS.get("*", set())
    if not bucket:
        return
    msg = {
        "type": event_type,
        "ts": time.time(),
        "payload": payload,
    }
    dead: list[WebSocket] = []
    for ws in list(bucket):
        try:
            await ws.send_text(json.dumps(msg, ensure_ascii=False))
        except Exception:
            dead.append(ws)
    for ws in dead:
        for s in _WS_CLIENTS.values():
            s.discard(ws)


@router.websocket("/workflow-definitions/ws")
async def definition_events_ws(websocket: WebSocket):
    await websocket.accept()
    bucket = _WS_CLIENTS.setdefault("*", set())
    bucket.add(websocket)
    try:
        # snapshot greeting; consumers expect a typed payload up front
        await websocket.send_text(
            json.dumps(
                {
                    "type": "snapshot",
                    "ts": time.time(),
                    "payload": {"events": list(_DOCUMENTED_EVENT_TYPES)},
                },
                ensure_ascii=False,
            )
        )
        while True:
            await asyncio.sleep(60)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.warning("workflow-definitions ws error: {}", exc)
    finally:
        for s in _WS_CLIENTS.values():
            s.discard(websocket)


_DOCUMENTED_EVENT_TYPES: tuple[str, ...] = (
    "workflow.updated",
    "workflow.deleted",
    "workflow.run.created",
    "workflow.run.step.event",
    "workflow.run.completed",
)


# ---------------------------------------------------------------------------
# Minimal definition diff for 409 payload


def _diff_definitions(
    *,
    your_definition: dict[str, Any] | None,
    current_definition: dict[str, Any] | None,
) -> dict[str, Any]:
    """Shallow diff that's enough for the UI to render `[查看 vN]` / `[强制覆盖]`.

    Lists field names that differ between the two payloads at the top level and
    the `steps` array length. The UI can drill into `current_definition` if the
    user picks `[查看 vN]`.
    """
    if not isinstance(your_definition, dict):
        your_definition = {}
    if not isinstance(current_definition, dict):
        current_definition = {}
    keys = set(your_definition) | set(current_definition)
    changed = [
        k
        for k in sorted(keys)
        if your_definition.get(k) != current_definition.get(k)
    ]
    your_steps = your_definition.get("steps") or []
    current_steps = current_definition.get("steps") or []
    return {
        "changed_top_level_keys": changed,
        "step_count_yours": len(your_steps) if isinstance(your_steps, list) else None,
        "step_count_current": len(current_steps) if isinstance(current_steps, list) else None,
    }
