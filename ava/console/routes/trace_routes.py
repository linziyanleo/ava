"""Trace span API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query

from ava.console import auth
from ava.console.models import UserInfo

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _get_trace_store(user: UserInfo):
    from ava.console.app import get_services_for_user

    svc = get_services_for_user(user)
    if svc.trace_spans is None:
        raise HTTPException(status_code=503, detail="Trace spans not available")
    return svc.trace_spans


@router.get("/traces")
async def list_traces(
    session_key: str | None = Query(None, description="Filter by session key"),
    turn_seq: int | None = Query(None, description="Filter by turn sequence"),
    limit: int = Query(50, ge=1, le=200),
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    return {
        "traces": _get_trace_store(user).list_traces(
            session_key=session_key,
            turn_seq=turn_seq,
            limit=limit,
        )
    }


@router.get("/traces/{trace_id}")
async def get_trace(
    trace_id: str,
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    trace = _get_trace_store(user).get_trace(trace_id)
    if not trace["spans"] and not trace["token_usage"]:
        raise HTTPException(status_code=404, detail="Trace not found")
    return trace
