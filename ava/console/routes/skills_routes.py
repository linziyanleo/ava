"""Skills and tools management routes."""

from __future__ import annotations

import json

from fastapi import APIRouter, Depends, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from ava.console import auth
from ava.console.middleware import get_client_ip
from ava.console.models import UserInfo

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


class NLMatchingUpdateRequest(BaseModel):
    enabled: bool


class MCPTestRequest(BaseModel):
    name: str


def _read_skills_block(svc) -> tuple[dict, dict, float]:
    """Return (full_console_config, skills_block, mtime). Defaults to {} when missing."""
    raw = svc.config.read_config("console-config.json", mask=False)
    payload: dict = {}
    try:
        payload = json.loads(raw.get("content") or "{}")
    except json.JSONDecodeError:
        payload = {}
    if not isinstance(payload, dict):
        payload = {}
    skills_block = payload.get("skills") if isinstance(payload.get("skills"), dict) else {}
    return payload, skills_block, float(raw.get("mtime", 0) or 0)


@router.get("/tools")
async def list_tools(
    user: UserInfo = Depends(auth.require_role(*auth.READ_ROLES)),
):
    """List all built-in tools."""
    from ava.console.app import get_services_for_user
    return {"tools": get_services_for_user(user).skills.list_tools()}


@router.get("/mcp/status")
async def mcp_status(
    user: UserInfo = Depends(auth.require_role(*auth.READ_ROLES)),
):
    """List configured MCP servers with redacted config and runtime status."""
    from ava.console.app import get_services_for_user
    svc = get_services_for_user(user)
    agent_loop = getattr(svc.chat, "_agent", None) if svc.chat else None
    return svc.skills.mcp_status(agent_loop=agent_loop)


@router.post("/mcp/test")
async def mcp_test(
    body: MCPTestRequest,
    request: Request,
    user: UserInfo = Depends(auth.require_role(*auth.EDIT_ROLES)),
):
    """Run a short independent MCP probe for a configured server."""
    from ava.console.app import get_services
    svc = get_services()

    try:
        result = await svc.skills.test_mcp_server(body.name)
        svc.audit.log(
            user=user.username, role=user.role,
            action="skill.mcp.test",
            target=body.name,
            ip=get_client_ip(request),
        )
        return result
    except ValueError as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.post("/mcp/reconnect")
async def mcp_reconnect(
    request: Request,
    user: UserInfo = Depends(auth.require_role("owner")),
):
    """Reconnect MCP servers if the runtime supports it."""
    from ava.console.app import get_services
    svc = get_services()
    agent_loop = getattr(svc.chat, "_agent", None) if svc.chat else None
    result = svc.skills.reconnect_mcp(agent_loop=agent_loop)
    svc.audit.log(
        user=user.username, role=user.role,
        action="skill.mcp.reconnect",
        target=result.get("scope", "all"),
        ip=get_client_ip(request),
    )
    if not result.get("ok") and result.get("status") == "unsupported":
        return JSONResponse(status_code=501, content=result)
    return result


@router.get("/list")
async def list_skills(
    user: UserInfo = Depends(auth.require_role(*auth.READ_ROLES)),
):
    """List all skills (ava + agents + builtin) with enabled state."""
    from ava.console.app import get_services_for_user
    return {"skills": get_services_for_user(user).skills.list_skills()}


@router.get("/detail/{name}")
async def get_skill(
    name: str,
    user: UserInfo = Depends(auth.require_role(*auth.READ_ROLES)),
):
    """Get skill details."""
    from ava.console.app import get_services_for_user
    skill = get_services_for_user(user).skills.get_skill(name)
    if not skill:
        raise HTTPException(status_code=404, detail=f"Skill '{name}' not found")
    return skill


@router.get("/nl_matching")
async def get_nl_matching(
    user: UserInfo = Depends(auth.require_role(*auth.READ_ROLES)),
):
    """Read the global natural-language skill matcher toggle from console-config.json."""
    from ava.console.app import get_services_for_user
    svc = get_services_for_user(user)
    _, skills_block, _ = _read_skills_block(svc)
    enabled = skills_block.get("natural_language_matching", True) is not False
    return {"enabled": enabled}


@router.put("/nl_matching")
async def put_nl_matching(
    body: NLMatchingUpdateRequest,
    request: Request,
    user: UserInfo = Depends(auth.require_role(*auth.EDIT_ROLES)),
):
    """Update the global natural-language skill matcher toggle in console-config.json.

    Refs: finding-chain-implementation-audit §7 P0#2.
    """
    from ava.console.app import get_services_for_user
    svc = get_services_for_user(user)
    payload, skills_block, mtime = _read_skills_block(svc)
    skills_block["natural_language_matching"] = bool(body.enabled)
    payload["skills"] = skills_block
    new_content = json.dumps(payload, indent=2, ensure_ascii=False)
    try:
        result = svc.config.update_config("console-config.json", new_content, mtime)
    except ValueError as exc:
        raise HTTPException(status_code=409, detail=str(exc))
    svc.audit.log(
        user=user.username, role=user.role,
        action="skill.nl_matching",
        target=f"enabled={'true' if body.enabled else 'false'}",
        ip=get_client_ip(request),
    )
    return {"enabled": bool(body.enabled), "mtime": result.get("mtime")}


@router.put("/toggle")
async def toggle_skill(
    body: ToggleSkillRequest,
    request: Request,
    user: UserInfo = Depends(auth.require_role(*auth.EDIT_ROLES)),
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
    user: UserInfo = Depends(auth.require_role(*auth.EDIT_ROLES)),
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
    user: UserInfo = Depends(auth.require_role(*auth.EDIT_ROLES)),
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
    user: UserInfo = Depends(auth.require_role(*auth.EDIT_ROLES)),
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
    user: UserInfo = Depends(auth.require_role("owner")),
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
