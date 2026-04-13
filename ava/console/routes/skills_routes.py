"""Skills and tools management routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from pydantic import BaseModel

from ava.console import auth
from ava.console.models import UserInfo
from ava.console.middleware import get_client_ip

router = APIRouter(prefix="/api/skills", tags=["skills"])


class InstallGitRequest(BaseModel):
    git_url: str
    name: str | None = None


class InstallPathRequest(BaseModel):
    source_path: str
    name: str | None = None


class DeleteSkillRequest(BaseModel):
    name: str


class ToggleSkillRequest(BaseModel):
    name: str
    enabled: bool


@router.get("/tools")
async def list_tools(
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    """List all built-in tools."""
    from ava.console.app import get_services_for_user
    return {"tools": get_services_for_user(user).skills.list_tools()}


@router.get("/list")
async def list_skills(
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    """List all skills (ava + agents + builtin) with enabled state."""
    from ava.console.app import get_services_for_user
    return {"skills": get_services_for_user(user).skills.list_skills()}


@router.get("/detail/{name}")
async def get_skill(
    name: str,
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    """Get skill details."""
    from ava.console.app import get_services_for_user
    skill = get_services_for_user(user).skills.get_skill(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return skill


@router.put("/toggle")
async def toggle_skill(
    body: ToggleSkillRequest,
    request: Request,
    user: UserInfo = Depends(auth.require_role("admin", "editor")),
):
    """Enable or disable a skill."""
    from ava.console.app import get_services
    svc = get_services()

    try:
        result = svc.skills.toggle_skill(body.name, body.enabled)
        svc.audit.log(
            user=user.username, role=user.role,
            action="skill.toggle",
            target=f"{body.name}:{'enabled' if body.enabled else 'disabled'}",
            ip=get_client_ip(request),
        )
        return result
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/install/git")
async def install_from_git(
    body: InstallGitRequest,
    request: Request,
    user: UserInfo = Depends(auth.require_role("admin", "editor")),
):
    """Install a skill from a Git repository."""
    from ava.console.app import get_services
    svc = get_services()

    try:
        result = svc.skills.install_skill_from_git(body.git_url, body.name)
        svc.audit.log(
            user=user.username, role=user.role, action="skill.install",
            target=f"git:{body.git_url}", ip=get_client_ip(request),
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=500, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/install/path")
async def install_from_path(
    body: InstallPathRequest,
    request: Request,
    user: UserInfo = Depends(auth.require_role("admin", "editor")),
):
    """Install a skill from a local path."""
    from ava.console.app import get_services
    svc = get_services()

    try:
        result = svc.skills.install_skill_from_path(body.source_path, body.name)
        svc.audit.log(
            user=user.username, role=user.role, action="skill.install",
            target=f"path:{body.source_path}", ip=get_client_ip(request),
        )
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/install/upload")
async def install_from_upload(
    request: Request,
    name: str = Form(...),
    files: list[UploadFile] = File(...),
    user: UserInfo = Depends(auth.require_role("admin", "editor")),
):
    """Install a skill from uploaded files (native file picker / webkitdirectory)."""
    from ava.console.app import get_services
    svc = get_services()

    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")

    file_map: dict[str, bytes] = {}
    for f in files:
        # webkitdirectory provides webkitRelativePath; fallback to filename
        rel_path = f.filename or "unknown"
        content = await f.read()
        file_map[rel_path] = content

    try:
        result = svc.skills.install_skill_from_upload(name, file_map)
        svc.audit.log(
            user=user.username, role=user.role, action="skill.install",
            target=f"upload:{name}", ip=get_client_ip(request),
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@router.delete("/delete")
async def delete_skill(
    body: DeleteSkillRequest,
    request: Request,
    user: UserInfo = Depends(auth.require_role("admin")),
):
    """Delete an ava/skills/ skill."""
    from ava.console.app import get_services
    svc = get_services()

    try:
        result = svc.skills.delete_skill(body.name)
        svc.audit.log(
            user=user.username, role=user.role, action="skill.delete",
            target=body.name, ip=get_client_ip(request),
        )
        return result
    except FileNotFoundError as e:
        raise HTTPException(status_code=404, detail=str(e))
    except PermissionError as e:
        raise HTTPException(status_code=403, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
