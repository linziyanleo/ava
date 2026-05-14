"""LAN Access routes."""

from __future__ import annotations

from urllib.parse import urlparse

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from fastapi.responses import FileResponse
from pydantic import BaseModel

from ava.console import auth
from ava.console.middleware import get_client_ip
from ava.console.models import UserInfo
from ava.console.services.lan_access_service import DEVICE_TOKEN_TTL_DAYS

router = APIRouter(prefix="/api/lan-access", tags=["lan-access"])


class LanAccessUpdateRequest(BaseModel):
    enabled: bool


class LanPairRequest(BaseModel):
    pin: str
    device_name: str = ""


class DeviceCapabilitiesRequest(BaseModel):
    capabilities: list[str]


@router.get("/status")
async def lan_access_status(
    user: UserInfo = Depends(
        auth.require_console_role_or_device_capability(
            console_roles=auth.READ_ROLES,
            device_capabilities=("read",),
        )
    ),
):
    from ava.console.app import get_services_for_user

    svc = get_services_for_user(user)
    payload = svc.lan_access.get_status()
    payload["mdns"] = svc.mdns.status().__dict__
    payload["tunnel"] = svc.tunnel.status().__dict__
    payload["https"] = svc.lan_https.status().__dict__
    payload["qr_payload"] = None
    return payload


@router.get("/discovery")
async def lan_access_discovery(
    user: UserInfo = Depends(
        auth.require_console_role_or_device_capability(
            console_roles=auth.READ_ROLES,
            device_capabilities=("read",),
        )
    ),
):
    from ava.console.app import get_services_for_user

    svc = get_services_for_user(user)
    return {
        "lan_urls": svc.lan_access.get_lan_urls(),
        "origins": sorted(svc.lan_access.allowed_lan_origins()),
        "mdns": svc.mdns.status().__dict__,
        "tunnel": svc.tunnel.status().__dict__,
        "https": svc.lan_https.status().__dict__,
    }


@router.put("/config")
async def update_lan_access_config(
    body: LanAccessUpdateRequest,
    request: Request,
    user: UserInfo = Depends(auth.require_role("owner")),
):
    from ava.console.app import get_services

    svc = get_services()
    status_payload = svc.lan_access.set_enabled(body.enabled)
    if body.enabled:
        svc.mdns.start()
    else:
        svc.mdns.stop()
        svc.tunnel.stop()
        svc.lan_https.disable()
    svc.network.reload()
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
    user: UserInfo = Depends(auth.require_role("owner")),
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
    ip = get_client_ip(request)
    user_agent = request.headers.get("user-agent", "")
    ip_decision = svc.pair_throttle.check_ip(ip)
    if not ip_decision.allowed:
        svc.lan_access.log_pair_failure(
            event="pair_throttled",
            ip=ip,
            user_agent=user_agent,
            pin_hash=svc.lan_access.current_pairing_hash(),
            reason=ip_decision.reason,
        )
        svc.audit.log(
            user="anonymous",
            role="none",
            action="lan.pair.throttled",
            target="lan-access",
            detail={"locked_until": ip_decision.locked_until, "reason": ip_decision.reason},
            ip=ip,
        )
        raise HTTPException(
            status_code=status.HTTP_429_TOO_MANY_REQUESTS,
            detail={"reason": "Pairing throttled", "locked_until": ip_decision.locked_until},
        )
    try:
        payload = svc.lan_access.pair_device(
            pin=body.pin,
            device_name=body.device_name,
            ip=ip,
            user_agent=user_agent,
        )
    except ValueError as exc:
        pin_hash = svc.lan_access.current_pairing_hash()
        decision = svc.pair_throttle.record_failure(ip=ip, pin_hash=pin_hash)
        if decision.reason == "pin":
            svc.lan_access.invalidate_pin("pair_lockout")
        svc.lan_access.log_pair_failure(
            event="pair_failed",
            ip=ip,
            user_agent=user_agent,
            pin_hash=pin_hash,
            reason=str(exc),
        )
        if not decision.allowed:
            svc.audit.log(
                user="anonymous",
                role="none",
                action="lan.pair.lockout",
                target="lan-access",
                detail={"locked_until": decision.locked_until, "reason": decision.reason},
                ip=ip,
            )
            raise HTTPException(
                status_code=status.HTTP_429_TOO_MANY_REQUESTS,
                detail={"reason": "Pairing locked", "locked_until": decision.locked_until},
            ) from exc
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
    auth.set_session_cookie(
        response,
        payload["access_token"],
        request,
        max_age_seconds=DEVICE_TOKEN_TTL_DAYS * 24 * 60 * 60,
    )
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
    user: UserInfo = Depends(auth.require_role("owner")),
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


@router.post("/devices/{device_id}/capability")
async def update_device_capabilities(
    device_id: str,
    body: DeviceCapabilitiesRequest,
    request: Request,
    user: UserInfo = Depends(auth.require_role("owner")),
):
    from ava.console.app import get_services

    svc = get_services()
    try:
        device = svc.lan_access.update_device_capabilities(device_id, body.capabilities)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Device not found: {device_id}") from exc
    svc.audit.log(
        user=user.username,
        role=user.role,
        action="lan.device.capability_update",
        target=device_id,
        detail={"capabilities": device["capabilities"]},
        ip=get_client_ip(request),
    )
    return device


@router.post("/devices/{device_id}/renew")
async def renew_device(
    device_id: str,
    request: Request,
    user: UserInfo = Depends(auth.require_role("owner")),
):
    from ava.console.app import get_services

    svc = get_services()
    try:
        device = svc.lan_access.renew_device(device_id)
    except KeyError as exc:
        raise HTTPException(status_code=404, detail=f"Device not found: {device_id}") from exc
    svc.audit.log(
        user=user.username,
        role=user.role,
        action="lan.device.renew",
        target=device_id,
        detail={"expires_at": device["expires_at"]},
        ip=get_client_ip(request),
    )
    return device


@router.post("/tunnel/{action}")
async def tunnel_action(
    action: str,
    request: Request,
    user: UserInfo = Depends(auth.require_role("owner")),
):
    from ava.console.app import get_services

    svc = get_services()
    if action == "start":
        payload = svc.tunnel.start().__dict__
    elif action == "stop":
        payload = svc.tunnel.stop().__dict__
    else:
        raise HTTPException(status_code=404, detail=f"Unknown tunnel action: {action}")
    svc.network.reload()
    svc.audit.log(
        user=user.username,
        role=user.role,
        action=f"lan.tunnel.{action}",
        target="lan-access",
        detail={"public_url": payload.get("public_url", "")},
        ip=get_client_ip(request),
    )
    return payload


@router.post("/https/{action}")
async def https_action(
    action: str,
    request: Request,
    user: UserInfo = Depends(auth.require_role("owner")),
):
    from ava.console.app import get_services

    svc = get_services()
    if action == "enable":
        hostname = ""
        if svc.tunnel.public_url:
            hostname = urlparse(svc.tunnel.public_url).hostname or ""
        payload = svc.lan_https.enable(tunnel_hostname=hostname).__dict__
    elif action == "disable":
        payload = svc.lan_https.disable().__dict__
    else:
        raise HTTPException(status_code=404, detail=f"Unknown HTTPS action: {action}")
    svc.network.reload()
    svc.audit.log(
        user=user.username,
        role=user.role,
        action=f"lan.https.{action}",
        target="lan-access",
        ip=get_client_ip(request),
    )
    return payload


@router.get("/cert/ca.crt")
async def download_ca_certificate(user: UserInfo = Depends(auth.require_role("owner"))):
    from ava.console.app import get_services

    path = get_services().lan_https.ca_certificate_path()
    if not path.exists():
        raise HTTPException(status_code=404, detail="LAN HTTPS CA certificate not generated")
    return FileResponse(path, media_type="application/x-x509-ca-cert", filename="ava-lan-ca.crt")
