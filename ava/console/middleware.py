"""CORS, origin, and audit logging middleware."""

from __future__ import annotations

import ipaddress
from typing import Any

from fastapi import FastAPI, HTTPException, Request, status
from starlette.responses import JSONResponse, Response

MUTATING_METHODS = {"POST", "PUT", "PATCH", "DELETE"}


def setup_cors(app: FastAPI) -> None:
    @app.middleware("http")
    async def dynamic_cors(request: Request, call_next):
        origin = request.headers.get("origin", "")
        if (
            request.method == "OPTIONS"
            and origin
            and request.headers.get("access-control-request-method")
        ):
            allowed = is_origin_allowed(origin)
            response = Response(status_code=200 if allowed else 403)
            if allowed:
                _apply_cors_headers(response, origin)
            return response

        if (
            request.url.path.startswith("/api/")
            and request.method in MUTATING_METHODS
            and origin
            and not is_origin_allowed(origin)
        ):
            _audit_blocked_origin(request, origin)
            return JSONResponse(
                {"detail": "Origin not allowed"},
                status_code=status.HTTP_403_FORBIDDEN,
            )

        response = await call_next(request)
        if origin and is_origin_allowed(origin):
            _apply_cors_headers(response, origin)
        return response


def _apply_cors_headers(response: Response, origin: str) -> None:
    response.headers["Access-Control-Allow-Origin"] = origin
    response.headers["Access-Control-Allow-Credentials"] = "true"
    response.headers["Access-Control-Allow-Methods"] = "GET,POST,PUT,PATCH,DELETE,OPTIONS"
    response.headers["Access-Control-Allow-Headers"] = "Authorization,Content-Type"
    response.headers["Vary"] = "Origin"


def origin_allowlist() -> set[str]:
    try:
        from ava.console.app import get_services

        svc = get_services()
    except Exception:
        return set()

    origins: set[str] = set()
    try:
        origins.update(svc.lan_access.allowed_lan_origins())
    except Exception:
        pass
    try:
        public_url = svc.tunnel.public_url
    except Exception:
        public_url = ""
    if public_url:
        origins.add(public_url.rstrip("/"))
    return origins


def is_origin_allowed(origin: str) -> bool:
    return origin.rstrip("/") in origin_allowlist()


def enforce_origin_allowlist(request: Request) -> None:
    origin = request.headers.get("origin", "")
    if origin and not is_origin_allowed(origin):
        _audit_blocked_origin(request, origin)
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Origin not allowed")


def is_ws_origin_allowed(headers: Any) -> bool:
    origin = headers.get("origin", "")
    return not origin or is_origin_allowed(origin)


def is_effective_https(request: Request) -> bool:
    if request.url.scheme == "https":
        return True
    try:
        from ava.console.app import get_services

        svc = get_services()
        tunnel_running = bool(svc.tunnel.running)
    except Exception:
        tunnel_running = False
    return (
        tunnel_running
        and _is_loopback(_client_host(request))
        and request.headers.get("x-forwarded-proto", "").lower() == "https"
    )


def get_client_ip(request) -> str:
    client_host = _client_host(request)
    try:
        from ava.console.app import get_services

        tunnel_running = bool(get_services().tunnel.running)
    except Exception:
        tunnel_running = False
    if tunnel_running and _is_loopback(client_host):
        cf_ip = request.headers.get("cf-connecting-ip", "").strip()
        if cf_ip:
            return cf_ip
    return client_host


def _client_host(request) -> str:
    if request.client:
        return request.client.host
    return ""


def _is_loopback(host: str) -> bool:
    try:
        return ipaddress.ip_address(host).is_loopback
    except ValueError:
        return host in {"localhost"}


def _audit_blocked_origin(request: Request, origin: str) -> None:
    try:
        from ava.console.app import get_services

        get_services().audit.log(
            user="unknown",
            role="unknown",
            action="lan.origin.blocked",
            target=request.url.path,
            detail={"origin": origin},
            ip=get_client_ip(request),
        )
    except Exception:
        pass
