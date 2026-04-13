"""File management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Query
from pydantic import BaseModel

from ava.console import auth
from ava.console.models import FileWriteRequest, UserInfo
from ava.console.middleware import get_client_ip

router = APIRouter(prefix="/api/files", tags=["files"])


class FileDeleteRequest(BaseModel):
    path: str


@router.get("/tree")
async def get_tree(
    root: str = Query("workspace", description="Root: 'workspace' or 'nanobot'"),
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    from ava.console.app import get_services_for_user
    try:
        return get_services_for_user(user).files.get_file_tree(root)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.get("/read")
async def read_file(
    path: str = Query(..., description="File path"),
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    from ava.console.app import get_services_for_user
    try:
        return get_services_for_user(user).files.read_file(path)
    except (FileNotFoundError, PermissionError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/write")
async def write_file(
    body: FileWriteRequest,
    request: Request,
    user: UserInfo = Depends(auth.require_role("admin", "editor", "mock_tester")),
):
    from ava.console.app import get_services_for_user

    svc = get_services_for_user(user)
    try:
        result = svc.files.write_file(body.path, body.content, body.expected_mtime)
    except (PermissionError, ValueError) as e:
        raise HTTPException(status_code=409 if "modified" in str(e).lower() else 403, detail=str(e))

    svc.audit.log(
        user=user.username, role=user.role, action="file.update",
        target=body.path, ip=get_client_ip(request),
    )
    return result


@router.delete("/delete")
async def delete_file(
    body: FileDeleteRequest,
    request: Request,
    user: UserInfo = Depends(auth.require_role("admin", "editor", "mock_tester")),
):
    from ava.console.app import get_services_for_user

    svc = get_services_for_user(user)
    try:
        svc.files.delete_file(body.path)
    except (FileNotFoundError, PermissionError, ValueError) as e:
        raise HTTPException(status_code=404, detail=str(e))

    svc.audit.log(
        user=user.username, role=user.role, action="file.delete",
        target=body.path, ip=get_client_ip(request),
    )
    return {"ok": True}
