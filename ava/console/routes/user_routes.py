"""User management routes (admin only)."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from ava.console import auth
from ava.console.models import UserCreateRequest, UserUpdateRequest, UserInfo
from ava.console.middleware import get_client_ip

router = APIRouter(prefix="/api/users", tags=["users"])


@router.get("")
async def list_users(user: UserInfo = Depends(auth.require_role("admin"))):
    from ava.console.app import get_services
    return get_services().users.list_users()


@router.post("")
async def create_user(
    body: UserCreateRequest,
    request: Request,
    user: UserInfo = Depends(auth.require_role("admin")),
):
    from ava.console.app import get_services

    svc = get_services()
    try:
        new_user = svc.users.create_user(body.username, body.password, body.role)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    svc.audit.log(
        user=user.username, role=user.role, action="user.create",
        target=body.username, detail={"role": body.role},
        ip=get_client_ip(request),
    )
    return new_user


@router.put("/{username}")
async def update_user(
    username: str,
    body: UserUpdateRequest,
    request: Request,
    user: UserInfo = Depends(auth.require_role("admin")),
):
    from ava.console.app import get_services

    svc = get_services()
    try:
        updated = svc.users.update_user(username, password=body.password, role=body.role)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))

    svc.audit.log(
        user=user.username, role=user.role, action="user.update",
        target=username, detail={"role_changed": body.role is not None},
        ip=get_client_ip(request),
    )
    return updated


@router.delete("/{username}")
async def delete_user(
    username: str,
    request: Request,
    user: UserInfo = Depends(auth.require_role("admin")),
):
    from ava.console.app import get_services

    if username == user.username:
        raise HTTPException(status_code=400, detail="Cannot delete yourself")

    svc = get_services()
    if not svc.users.delete_user(username):
        raise HTTPException(status_code=404, detail="User not found")

    svc.audit.log(
        user=user.username, role=user.role, action="user.delete",
        target=username, ip=get_client_ip(request),
    )
    return {"ok": True}
