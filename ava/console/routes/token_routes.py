"""Token usage statistics API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ava.console import auth
from ava.console.models import UserInfo

router = APIRouter(prefix="/api/stats", tags=["stats"])


def _get_collector(user: UserInfo):
    from ava.console.app import get_services_for_user
    svc = get_services_for_user(user)
    if svc.token_stats is None:
        from fastapi import HTTPException
        raise HTTPException(status_code=503, detail="Token stats not available")
    return svc.token_stats


@router.get("/tokens")
async def get_token_stats(
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    """Token usage summary: totals + by_model + by_provider."""
    return _get_collector(user).get_summary()


@router.get("/tokens/records")
async def get_token_records(
    limit: int = Query(100, ge=1, le=1000),
    offset: int = Query(0, ge=0),
    session_key: str | None = Query(None, description="Filter by session key"),
    conversation_id: str | None = Query(None, description="Filter by logical conversation id"),
    model: str | None = Query(None, description="Filter by model (substring match)"),
    provider: str | None = Query(None, description="Filter by provider (substring match)"),
    start_time: str | None = Query(None, description="Filter: timestamp >= ISO string"),
    end_time: str | None = Query(None, description="Filter: timestamp <= ISO string"),
    turn_seq: int | None = Query(None, description="Filter by turn sequence number"),
    model_role: str | None = Query(None, description="Filter by model role (e.g. claude_code, chat, mini, voice, vision)"),
    trace_id: str | None = Query(None, description="Filter by trace id"),
    span_id: str | None = Query(None, description="Filter by span id"),
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    """Individual LLM call records (newest first), with optional filters."""
    collector = _get_collector(user)
    filt = dict(
        session_key=session_key,
        conversation_id=conversation_id,
        model=model,
        provider=provider,
        start_time=start_time,
        end_time=end_time,
        turn_seq=turn_seq,
        model_role=model_role,
        trace_id=trace_id,
        span_id=span_id,
    )
    return {
        "records": collector.get_records(limit=limit, offset=offset, **filt),
        "total": collector.get_total_count(**filt),
    }


@router.get("/tokens/by-model")
async def get_tokens_by_model(
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    """Token usage aggregated by model."""
    return _get_collector(user).get_by_model()


@router.get("/tokens/by-provider")
async def get_tokens_by_provider(
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    """Token usage aggregated by provider."""
    return _get_collector(user).get_by_provider()


@router.get("/tokens/by-session")
async def get_tokens_by_session(
    session_key: str = Query(..., description="Session key (e.g. telegram:12345)"),
    conversation_id: str | None = Query(None, description="Logical conversation id"),
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    """Per-turn token aggregation for a specific session."""
    return _get_collector(user).get_by_session(session_key, conversation_id=conversation_id)


@router.get("/tokens/by-session/detailed")
async def get_tokens_by_session_detailed(
    session_key: str = Query(..., description="Session key"),
    conversation_id: str | None = Query(None, description="Logical conversation id"),
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    """Per-iteration token records for a specific session (no aggregation)."""
    return _get_collector(user).get_by_session_detailed(session_key, conversation_id=conversation_id)


@router.get("/tokens/timeline")
async def get_token_timeline(
    interval: str = Query("hour", pattern="^(hour|day)$"),
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    """Token usage aggregated by time interval."""
    return _get_collector(user).get_timeline(interval=interval)


@router.post("/tokens/reset")
async def reset_token_stats(
    user: UserInfo = Depends(auth.require_role("admin")),
):
    """Reset all token stats (admin only)."""
    _get_collector(user).reset()
    return {"status": "ok", "message": "Token stats cleared"}
