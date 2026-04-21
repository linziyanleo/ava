"""Background task status API — REST + WebSocket real-time updates."""

from __future__ import annotations

import asyncio
import json

from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect
from loguru import logger
from ava.console import auth
from ava.console.models import UserInfo

router = APIRouter(prefix="/api/bg-tasks", tags=["bg-tasks"])


def _get_bg_store(user: UserInfo | None = None):
    from ava.console.app import get_services_for_user
    svc = get_services_for_user(user)
    agent_loop = getattr(svc.chat, "_agent", None) if svc.chat else None
    return getattr(agent_loop, "bg_tasks", None) if agent_loop else None


@router.get("")
async def list_tasks(
    session_key: str | None = None,
    workspace_id: str | None = None,
    workspace_key: str | None = None,
    include_finished: bool = True,
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    bg_store = _get_bg_store(user)
    if not bg_store:
        return {"running": 0, "total": 0, "tasks": []}

    if workspace_id:
        tasks = bg_store.find_active_by_workspace(workspace_id)
        return {"running": len(tasks), "total": len(tasks), "tasks": [t.to_dict() for t in tasks]}
    if workspace_key:
        tasks = bg_store.find_active_by_target(workspace_key)
        return {"running": len(tasks), "total": len(tasks), "tasks": [t.to_dict() for t in tasks]}

    return bg_store.get_status(
        session_key=session_key,
        include_finished=include_finished,
    )


@router.get("/history")
async def list_history(
    page: int = 1,
    page_size: int = 20,
    session_key: str | None = None,
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    bg_store = _get_bg_store(user)
    if not bg_store:
        return {"tasks": [], "total": 0, "page": page, "page_size": page_size}
    return bg_store.query_history(page=page, page_size=page_size, session_key=session_key)


@router.get("/{task_id}")
async def get_task(task_id: str, user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester"))):
    bg_store = _get_bg_store(user)
    if not bg_store:
        return {"error": "BackgroundTaskStore not initialized"}
    status = bg_store.get_status(task_id=task_id)
    if status["total"] == 0:
        return {"error": f"Task {task_id} not found"}
    return status["tasks"][0]


@router.get("/{task_id}/detail")
async def get_task_detail(task_id: str, user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester"))):
    """获取任务的完整 prompt、result 和 workspace metadata。"""
    bg_store = _get_bg_store(user)
    if not bg_store:
        return {"error": "BackgroundTaskStore not initialized"}
    detail = bg_store.get_task_detail(task_id)
    if not detail:
        return {"error": f"Task {task_id} not found"}

    status = bg_store.get_status(task_id=task_id)
    if status["tasks"]:
        task_dict = status["tasks"][0]
        detail["workspace"] = {
            "workspace_id": task_dict.get("workspace_id", ""),
            "workspace_key": task_dict.get("workspace_key", ""),
            "execution_cwd": task_dict.get("execution_cwd", ""),
            "isolation_mode": task_dict.get("isolation_mode", "inplace"),
            "branch_name": task_dict.get("branch_name", ""),
            "worktree_path": task_dict.get("worktree_path", ""),
        }
    return detail


@router.get("/{task_id}/timeline")
async def get_timeline(task_id: str, user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester"))):
    bg_store = _get_bg_store(user)
    if not bg_store:
        return {"events": []}
    events = bg_store.get_timeline(task_id)
    return {
        "task_id": task_id,
        "events": [
            {"timestamp": e.timestamp, "event": e.event, "detail": e.detail}
            for e in events
        ],
    }


@router.post("/{task_id}/cancel")
async def cancel_task(task_id: str, user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester"))):
    bg_store = _get_bg_store(user)
    if not bg_store:
        return {"message": "BackgroundTaskStore not initialized"}
    result = await bg_store.cancel(task_id)
    return {"message": result}


@router.websocket("/ws")
async def bg_tasks_ws(websocket: WebSocket):
    """Push task status snapshots at 2 s intervals; skip if unchanged."""
    user = await auth.get_ws_user(websocket)
    await websocket.accept()
    bg_store = _get_bg_store(user)

    if not bg_store:
        await websocket.send_json({"type": "update", "running": 0, "total": 0, "tasks": []})
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        return

    prev_snapshot: str = ""
    try:
        while True:
            status = bg_store.get_status(include_finished=True)
            snapshot_json = json.dumps(status, default=str)
            if snapshot_json != prev_snapshot:
                await websocket.send_json({"type": "update", **status})
                prev_snapshot = snapshot_json
            await asyncio.sleep(2)
    except WebSocketDisconnect:
        pass
    except Exception as exc:
        logger.debug("bg_tasks_ws closed: {}", exc)
