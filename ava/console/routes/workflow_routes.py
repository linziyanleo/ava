"""Workflow chain and task artifact API routes."""

from __future__ import annotations

import asyncio
import json
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, WebSocket, WebSocketDisconnect
from loguru import logger

from ava.agent.workflow_store import ArtifactStore, WorkflowStore
from ava.console import auth
from ava.console.app import get_services_for_user
from ava.console.models import UserInfo

router = APIRouter(prefix="/api", tags=["workflows"])


def _workflow_store(user: UserInfo) -> WorkflowStore:
    store = get_services_for_user(user).workflow_store
    if store is None:
        raise HTTPException(status_code=503, detail="WorkflowStore not initialized")
    return store


def _artifact_store(user: UserInfo) -> ArtifactStore:
    store = get_services_for_user(user).artifact_store
    if store is None:
        raise HTTPException(status_code=503, detail="ArtifactStore not initialized")
    return store


def _workflow_event_payload(
    workflow_store: WorkflowStore,
    artifact_store: ArtifactStore,
    *,
    trace_id: str | None = None,
    chain_id: str | None = None,
    task_id: str | None = None,
    artifact_type: str | None = None,
) -> dict[str, Any]:
    if chain_id:
        chain = workflow_store.get_chain(chain_id)
        chains = [chain] if chain is not None else []
    else:
        chains = workflow_store.list_chains(trace_id=trace_id, limit=50)
    artifacts = artifact_store.list_artifacts(
        task_id=task_id,
        chain_id=chain_id,
        trace_id=trace_id,
        artifact_type=artifact_type,
    )
    return {
        "type": "workflow_events",
        "chain_event": {"event": "snapshot", "count": len(chains)},
        "artifact_event": {"event": "snapshot", "count": len(artifacts)},
        "chains": [chain.to_dict() for chain in chains],
        "artifacts": [artifact.to_dict() for artifact in artifacts],
    }


@router.get("/workflows")
async def list_workflows(
    trace_id: str | None = None,
    status: str | None = None,
    limit: int = 50,
    user: UserInfo = Depends(auth.require_role(*auth.READ_ROLES)),
):
    store = _workflow_store(user)
    chains = store.list_chains(trace_id=trace_id, status=status, limit=limit)
    return {"chains": [chain.to_dict() for chain in chains]}


@router.post("/workflows")
async def create_workflow(
    payload: dict[str, Any],
    user: UserInfo = Depends(auth.require_role(*auth.EDIT_ROLES)),
):
    store = _workflow_store(user)
    chain = store.register_chain(
        chain_id=payload.get("chain_id") or None,
        trace_id=str(payload.get("trace_id") or ""),
        title=str(payload.get("title") or ""),
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
    )
    return chain.to_dict()


@router.get("/workflows/{chain_id}")
async def get_workflow(
    chain_id: str,
    user: UserInfo = Depends(auth.require_role(*auth.READ_ROLES)),
):
    store = _workflow_store(user)
    chain = store.get_chain(chain_id)
    if chain is None:
        raise HTTPException(status_code=404, detail=f"Workflow chain not found: {chain_id}")
    artifacts = _artifact_store(user).list_artifacts(chain_id=chain_id)
    data = chain.to_dict()
    data["artifacts"] = [artifact.to_dict() for artifact in artifacts]
    return data


@router.post("/workflows/{chain_id}/nodes")
async def upsert_workflow_node(
    chain_id: str,
    payload: dict[str, Any],
    user: UserInfo = Depends(auth.require_role(*auth.EDIT_ROLES)),
):
    store = _workflow_store(user)
    task_id = str(payload.get("task_id") or "")
    if not task_id:
        raise HTTPException(status_code=400, detail="task_id is required")
    parent_task_ids = payload.get("parent_task_ids")
    node = store.upsert_node(
        chain_id=chain_id,
        task_id=task_id,
        status=payload.get("status") or "pending",
        parent_task_ids=parent_task_ids if isinstance(parent_task_ids, list) else None,
        node_kind=str(payload.get("node_kind") or ""),
        title=str(payload.get("title") or ""),
        position=payload.get("position") if isinstance(payload.get("position"), int) else None,
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
    )
    store.advance_linear_chain(chain_id)
    return node.to_dict()


@router.post("/workflows/{chain_id}/advance")
async def advance_workflow(
    chain_id: str,
    user: UserInfo = Depends(auth.require_role(*auth.EDIT_ROLES)),
):
    store = _workflow_store(user)
    chain = store.advance_linear_chain(chain_id)
    if chain is None:
        raise HTTPException(status_code=404, detail=f"Workflow chain not found: {chain_id}")
    return chain.to_dict()


@router.post("/workflows/{chain_id}/cancel")
async def cancel_workflow(
    chain_id: str,
    user: UserInfo = Depends(auth.require_role(*auth.EDIT_ROLES)),
):
    store = _workflow_store(user)
    chain = store.cancel_chain(chain_id)
    if chain is None:
        raise HTTPException(status_code=404, detail=f"Workflow chain not found: {chain_id}")
    return chain.to_dict()


@router.post("/workflows/{chain_id}/retry")
async def retry_workflow(
    chain_id: str,
    user: UserInfo = Depends(auth.require_role(*auth.EDIT_ROLES)),
):
    store = _workflow_store(user)
    chain = store.retry_chain(chain_id)
    if chain is None:
        raise HTTPException(status_code=404, detail=f"Workflow chain not found: {chain_id}")
    return chain.to_dict()


@router.get("/artifacts")
async def list_artifacts(
    task_id: str | None = None,
    chain_id: str | None = None,
    trace_id: str | None = None,
    artifact_type: str | None = None,
    limit: int = 100,
    user: UserInfo = Depends(auth.require_role(*auth.READ_ROLES)),
):
    store = _artifact_store(user)
    artifacts = store.list_artifacts(
        task_id=task_id,
        chain_id=chain_id,
        trace_id=trace_id,
        artifact_type=artifact_type,
        limit=limit,
    )
    return {"artifacts": [artifact.to_dict() for artifact in artifacts]}


@router.post("/artifacts")
async def create_artifact(
    payload: dict[str, Any],
    user: UserInfo = Depends(auth.require_role(*auth.EDIT_ROLES)),
):
    store = _artifact_store(user)
    task_id = str(payload.get("task_id") or "")
    uri = str(payload.get("uri") or "")
    if not task_id or not uri:
        raise HTTPException(status_code=400, detail="task_id and uri are required")
    artifact = store.record_artifact(
        artifact_id=payload.get("artifact_id") or None,
        task_id=task_id,
        artifact_type=payload.get("artifact_type") or "text",
        uri=uri,
        chain_id=str(payload.get("chain_id") or ""),
        trace_id=str(payload.get("trace_id") or ""),
        preview=str(payload.get("preview") or ""),
        metadata=payload.get("metadata") if isinstance(payload.get("metadata"), dict) else None,
    )
    return artifact.to_dict()


@router.websocket("/workflows/ws")
async def workflow_events_ws(websocket: WebSocket):
    user = await auth.get_ws_user(websocket)
    await websocket.accept()
    svc = get_services_for_user(user)
    workflow_store = svc.workflow_store
    artifact_store = svc.artifact_store
    if workflow_store is None or artifact_store is None:
        await websocket.send_json({
            "type": "workflow_events",
            "chain_event": {"event": "unavailable", "count": 0},
            "artifact_event": {"event": "unavailable", "count": 0},
            "chains": [],
            "artifacts": [],
        })
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        return

    query = websocket.query_params
    trace_id = query.get("trace_id")
    chain_id = query.get("chain_id")
    task_id = query.get("task_id")
    artifact_type = query.get("artifact_type")
    prev_snapshot = ""
    try:
        while True:
            payload = _workflow_event_payload(
                workflow_store,
                artifact_store,
                trace_id=trace_id,
                chain_id=chain_id,
                task_id=task_id,
                artifact_type=artifact_type,
            )
            snapshot = json.dumps(payload, sort_keys=True, default=str)
            if snapshot != prev_snapshot:
                await websocket.send_json(payload)
                prev_snapshot = snapshot
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("workflow_events_ws closed: {}", exc)
