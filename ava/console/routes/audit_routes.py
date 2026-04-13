"""Audit log query routes (admin only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from ava.console import auth
from ava.console.models import UserInfo

router = APIRouter(prefix="/api/audit", tags=["audit"])


@router.get("/logs")
async def query_logs(
    page: int = Query(1, ge=1),
    size: int = Query(50, ge=1, le=200),
    user: str | None = Query(None),
    action: str | None = Query(None),
    current_user: UserInfo = Depends(auth.require_role("admin")),
):
    from ava.console.app import get_services
    return get_services().audit.query(page=page, size=size, user=user, action=action)
