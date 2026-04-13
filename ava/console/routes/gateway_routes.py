"""Gateway control routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, Request

from ava.console import auth
from ava.console.models import GatewayRestartRequest, UserInfo
from ava.console.middleware import get_client_ip

router = APIRouter(prefix="/api/gateway", tags=["gateway"])


@router.post("/console/rebuild")
async def console_rebuild(
    request: Request,
    user: UserInfo = Depends(auth.require_role("admin")),
):
    """触发 console-ui 前端重建（零中断，不影响 gateway 进程）。"""
    from ava.console.app import get_services
    from ava.console.ui_build import rebuild_console_ui

    svc = get_services()
    svc.audit.log(
        user=user.username, role=user.role, action="console.rebuild",
        target="console-ui", detail={},
        ip=get_client_ip(request),
    )
    result = await rebuild_console_ui()
    return {
        "success": result.success,
        "duration_ms": result.duration_ms,
        "version_hash": result.version_hash,
        "error": result.error,
        "log_tail": result.log_tail,
    }


@router.get("/status")
async def gateway_status(user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester"))):
    from ava.console.app import get_services_for_user
    return get_services_for_user(user).gateway.get_status()


@router.get("/health")
async def gateway_health():
    """Health check 端点，无需认证，供 supervisor 和 restart verification 使用。"""
    from ava.console.app import get_services
    return get_services().gateway.health()


@router.post("/restart")
async def gateway_restart(
    body: GatewayRestartRequest,
    request: Request,
    user: UserInfo = Depends(auth.require_role("admin")),
):
    from ava.console.app import get_services

    svc = get_services()
    svc.audit.log(
        user=user.username, role=user.role, action="gateway.restart",
        target="gateway", detail={"delay_ms": body.delay_ms, "force": body.force},
        ip=get_client_ip(request),
    )
    return await svc.gateway.restart(delay_ms=body.delay_ms, force=body.force)
