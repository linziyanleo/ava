"""LAN Access routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel

from ava.console import auth
from ava.console.middleware import get_client_ip
from ava.console.models import UserInfo

router = APIRouter(prefix="/api/lan-access", tags=["lan-access"])


class LanAccessUpdateRequest(BaseModel):
    enabled: bool


class LanPairRequest(BaseModel):
    pin: str
    device_name: str = ""


@router.get("/status")
async def lan_access_status(user: UserInfo = Depends(auth.require_role(*auth.READ_ROLES))):
    from ava.console.app import get_services_for_user
    return get_services_for_user(user).lan_access.get_status()


@router.put("/config")
async def update_lan_access_config(
    body: LanAccessUpdateRequest,
    request: Request,
    user: UserInfo = Depends(auth.require_role("admin")),
):
    from ava.console.app import get_services

    svc = get_services()
    status_payload = svc.lan_access.set_enabled(body.enabled)
    svc.audit.log(
        user=user.username,
        role=user.role,
        action="lan.config.update",
        target="lan-access",
        detail={
            "enabled": body.enabled,
            "bind_host": status_payload["bind_host"],
        },
        ip=get_client_ip(request),
    )
    return status_payload


@router.post("/pin")
async def create_pairing_pin(
    request: Request,
    user: UserInfo = Depends(auth.require_role("admin")),
):
    from ava.console.app import get_services

    svc = get_services()
    try:
        payload = svc.lan_access.create_pairing_pin()
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc)) from exc
    svc.audit.log(
        user=user.username,
        role=user.role,
        action="lan.pin.create",
        target="lan-access",
        detail={"expires_at": payload["expires_at"]},
        ip=get_client_ip(request),
    )
    return payload


@router.post("/pair")
async def pair_device(body: LanPairRequest, request: Request, response: Response):
    from ava.console.app import get_services

    svc = get_services()
    try:
        payload = svc.lan_access.pair_device(
            pin=body.pin,
            device_name=body.device_name,
            ip=get_client_ip(request),
            user_agent=request.headers.get("user-agent", ""),
        )
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    auth.set_session_cookie(response, payload["access_token"])
    svc.audit.log(
        user=f"device:{payload['device']['device_id']}",
        role="read_only",
        action="lan.device.pair",
        target="lan-access",
        detail={"device_name": payload["device"]["name"]},
        ip=get_client_ip(request),
    )
    return payload


@router.post("/devices/{device_id}/revoke")
async def revoke_device(
    device_id: str,
    request: Request,
    user: UserInfo = Depends(auth.require_role("admin")),
):
    from ava.console.app import get_services

    svc = get_services()
    try:
        device = svc.lan_access.revoke_device(device_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Device not found: {device_id}") from exc
    svc.audit.log(
        user=user.username,
        role=user.role,
        action="lan.device.revoke",
        target=device_id,
        ip=get_client_ip(request),
    )
    return device
