"""Agent registry API routes."""

from __future__ import annotations

from pathlib import Path

from fastapi import APIRouter, Depends, HTTPException

from ava.console import auth
from ava.console.models import UserInfo
from ava.console.services.agent_registry_service import AgentRegistryService

router = APIRouter(prefix="/api", tags=["agents"])


@router.get("/agents")
async def list_agents(
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    from ava.console.app import get_services_for_user

    svc = get_services_for_user(user)
    chat = svc.chat
    agent_loop = getattr(chat, "_agent", None) if chat else None
    bg_store = getattr(agent_loop, "bg_tasks", None) if agent_loop else None
    sessions_dir = getattr(chat, "_sessions_dir", None) if chat else None
    workspace = sessions_dir.parent if sessions_dir else Path.cwd()
    service = AgentRegistryService(
        agent_loop=agent_loop,
        workspace=workspace,
        bg_store=bg_store,
        media_service=svc.media,
        db=svc.db,
    )
    return service.list_agents()


@router.get("/agents/{agent_name}/version")
async def get_agent_version(
    agent_name: str,
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    from ava.console.app import get_services_for_user

    svc = get_services_for_user(user)
    chat = svc.chat
    agent_loop = getattr(chat, "_agent", None) if chat else None
    bg_store = getattr(agent_loop, "bg_tasks", None) if agent_loop else None
    sessions_dir = getattr(chat, "_sessions_dir", None) if chat else None
    workspace = sessions_dir.parent if sessions_dir else Path.cwd()
    payload = AgentRegistryService(
        agent_loop=agent_loop,
        workspace=workspace,
        bg_store=bg_store,
        media_service=svc.media,
        db=svc.db,
    ).list_agents()
    for agent in payload["agents"]:
        if agent["name"] == agent_name or agent["instance_id"] == agent_name:
            return {
                "name": agent["name"],
                "instance_id": agent["instance_id"],
                "version": agent["version"],
                "path": agent["path"],
                "installed": agent["installed"],
                "status": agent["status"],
            }
    raise HTTPException(status_code=404, detail=f"Unknown agent: {agent_name}")


@router.post("/agents/{agent_name}/tasks/cancel")
async def cancel_agent_tasks(
    agent_name: str,
    user: UserInfo = Depends(auth.require_role("admin", "editor")),
):
    from ava.console.app import get_services_for_user

    svc = get_services_for_user(user)
    chat = svc.chat
    agent_loop = getattr(chat, "_agent", None) if chat else None
    bg_store = getattr(agent_loop, "bg_tasks", None) if agent_loop else None
    sessions_dir = getattr(chat, "_sessions_dir", None) if chat else None
    workspace = sessions_dir.parent if sessions_dir else Path.cwd()
    return await AgentRegistryService(
        agent_loop=agent_loop,
        workspace=workspace,
        bg_store=bg_store,
        media_service=svc.media,
        db=svc.db,
    ).cancel_agent_tasks(agent_name)


@router.get("/core/version")
async def get_core_version(
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    return {
        "name": "ava-core",
        "version": "0.1.0",
        "protocol_version": "agent-adapter/0.1",
        "user": user.username,
    }
