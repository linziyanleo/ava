"""Console direct background task API."""

from __future__ import annotations

from pathlib import Path
from typing import Any, Literal

from fastapi import APIRouter, Depends, HTTPException, Request, status
from pydantic import BaseModel, Field

from ava.console import auth
from ava.console.middleware import get_client_ip
from ava.console.models import UserInfo
from ava.console.services.direct_task_service import DirectTaskService
from ava.console.services.trace_context import end_span_sync, start_span_sync

router = APIRouter(prefix="/api/console", tags=["direct-tasks"])


class DirectTaskSubmitRequest(BaseModel):
    task_type: Literal["codex", "claude_code", "image_gen"]
    prompt: str
    session_key: str
    conversation_id: str | None = None
    turn_seq: int | None = None
    project_path: str | None = None
    params: dict[str, Any] = Field(default_factory=dict)


@router.post("/direct-tasks", status_code=status.HTTP_201_CREATED)
async def submit_direct_task(
    body: DirectTaskSubmitRequest,
    request: Request,
    user: UserInfo = Depends(auth.require_role("admin", "editor")),
):
    from ava.console.app import get_services_for_user

    svc = get_services_for_user(user)
    chat = svc.chat
    agent_loop = getattr(chat, "_agent", None) if chat else None
    bg_store = getattr(agent_loop, "bg_tasks", None) if agent_loop else None
    if not agent_loop or not bg_store:
        raise HTTPException(status_code=503, detail="Background task runtime unavailable")

    workspace = getattr(chat, "_sessions_dir", None)
    workspace_root = workspace.parent if workspace else Path.cwd()
    service = DirectTaskService(
        agent_loop=agent_loop,
        workspace=workspace_root,
        bg_store=bg_store,
        token_stats=svc.token_stats,
        media_service=svc.media,
    )

    trace_ctx = None
    trace_token = None
    trace_store = svc.trace_spans

    def finish_trace(status_text: str, message: str = "") -> None:
        nonlocal trace_token
        if trace_ctx is None:
            return
        end_span_sync(
            trace_ctx,
            store=trace_store,
            status=status_text,
            status_message=message[:500],
            ctx_token=trace_token,
        )
        trace_token = None

    try:
        if trace_store is not None:
            trace_ctx, trace_token = start_span_sync(
                name="console.direct_task.submit",
                operation_name="console.direct_task.submit",
                store=trace_store,
                session_key=body.session_key,
                conversation_id=body.conversation_id or "",
                turn_seq=body.turn_seq,
                attributes={
                    "ava.task_type": body.task_type,
                    "ava.project_path": body.project_path or "",
                    "ava.console_user": user.username,
                },
            )
        result = await service.submit(
            task_type=body.task_type,
            prompt=body.prompt,
            session_key=body.session_key,
            conversation_id=body.conversation_id or "",
            turn_seq=body.turn_seq,
            project_path=body.project_path,
            params=body.params,
        )
    except ValueError as exc:
        finish_trace("error", str(exc))
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except RuntimeError as exc:
        finish_trace("error", str(exc))
        raise HTTPException(status_code=503, detail=str(exc)) from exc
    except Exception as exc:
        finish_trace("error", str(exc))
        raise
    else:
        if trace_ctx is not None:
            result["trace_id"] = trace_ctx.trace_id
            finish_trace("ok")
    finally:
        if trace_token is not None:
            finish_trace("error", "Direct task submit did not finish cleanly")

    svc.audit.log(
        user=user.username,
        role=user.role,
        action="console.direct_task.submit",
        target=result["task_id"],
        detail={
            "task_type": body.task_type,
            "session_key": body.session_key,
        },
        ip=get_client_ip(request),
    )
    return result
