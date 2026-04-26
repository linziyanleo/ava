"""Media gallery routes: image generation records and file serving."""

from __future__ import annotations

import mimetypes

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import FileResponse

from ava.console import auth
from ava.console.models import UserInfo
from ava.console.middleware import get_client_ip

router = APIRouter(prefix="/api/media", tags=["media"])


def _get_media_service():
    from ava.console.app import get_services
    return get_services().media


@router.get("/records")
async def list_records(
    page: int = Query(1, ge=1),
    size: int = Query(20, ge=1, le=100),
    search: str | None = Query(None),
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    from ava.console.app import get_services_for_user
    return get_services_for_user(user).media.query(page=page, size=size, search=search)


@router.get("/images/{filename}")
async def get_image(
    filename: str,
    user: UserInfo | None = Depends(auth.optional_user),
):
    """Serve generated image files to authenticated users."""
    if user is None:
        raise HTTPException(status_code=401, detail="Authentication required")

    from ava.console.app import get_services_for_user
    path = get_services_for_user(user).media.get_image_path(filename)
    if path is None:
        raise HTTPException(status_code=404, detail="Image not found")
    media_type = mimetypes.guess_type(path.name)[0] or "application/octet-stream"
    return FileResponse(str(path), media_type=media_type)


@router.delete("/records/{record_id}")
async def delete_record(
    record_id: str,
    request: Request,
    user: UserInfo = Depends(auth.require_role("admin", "editor", "mock_tester")),
):
    """Delete a media record and its associated image files."""
    from ava.console.app import get_services_for_user

    svc = get_services_for_user(user)
    try:
        svc.media.delete_record(record_id)
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))
    
    svc.audit.log(
        user=user.username, role=user.role, action="media.delete",
        target=record_id, ip=get_client_ip(request),
    )
    return {"ok": True}
