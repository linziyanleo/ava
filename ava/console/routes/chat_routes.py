"""Chat routes: WebSocket conversations + session management."""

from __future__ import annotations

import asyncio
import json
import re
from pathlib import Path

from loguru import logger
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect, status
from nanobot.bus.events import OutboundMessage

from ava.agents.nanobot.skill_matcher import natural_language_skill_matching, skill_match_narration
from ava.console import auth
from ava.console.middleware import get_client_ip
from ava.console.models import ChatSessionCreateRequest, ChatSessionUpdateRequest, UserInfo

router = APIRouter(prefix="/api/chat", tags=["chat"])
messages_router = APIRouter(prefix="/api", tags=["chat"])

_EMPTY_LISTENER_CONTENTS = {"(empty)", "[empty message]"}
_DIRECT_TASK_MENTION_RE = re.compile(
    r"(^|\s)@(codex|claude_code|claude-code)(?=\s|$)",
    re.IGNORECASE,
)
_DIRECT_TASK_AGENT_ALIASES = {
    "codex": "codex",
    "claude_code": "claude_code",
    "claude-code": "claude_code",
}
_SKILL_TRIGGER_RE = re.compile(r"^@([A-Za-z0-9_-]+)(?:\s+([\s\S]*))?$")


def _extract_direct_task_mention(content: str) -> tuple[str, str, list[str]] | None:
    match = _DIRECT_TASK_MENTION_RE.search(content)
    if not match:
        return None
    task_type = _DIRECT_TASK_AGENT_ALIASES[match.group(2).lower()]
    prompt = re.sub(r"\s+", " ", content[: match.start()] + " " + content[match.end() :]).strip()
    if not prompt:
        return None
    mentions = []
    for item in _DIRECT_TASK_MENTION_RE.finditer(content):
        agent_id = _DIRECT_TASK_AGENT_ALIASES[item.group(2).lower()]
        if agent_id not in mentions:
            mentions.append(agent_id)
    return task_type, prompt, mentions


def _parse_skill_trigger(content: str) -> tuple[str, str] | None:
    match = _SKILL_TRIGGER_RE.match(content.strip())
    if not match:
        return None
    skill_name = match.group(1).strip()
    if not skill_name:
        return None
    if skill_name.lower() in _DIRECT_TASK_AGENT_ALIASES:
        return None
    return skill_name, (match.group(2) or "").strip()


def _read_skill_content(skill: dict[str, object]) -> str:
    raw_path = skill.get("path")
    if not isinstance(raw_path, str) or not raw_path:
        return ""
    return Path(raw_path).read_text(encoding="utf-8")


async def _route_skill_trigger(
    *,
    svc_chat,
    skills_service,
    session_id: str,
    skill_name: str,
    prompt: str,
    user_id: str,
    on_progress,
    on_stream,
    on_stream_end,
) -> str:
    skill = skills_service.get_skill(skill_name) if skills_service is not None else None
    if not skill:
        raise KeyError(skill_name)
    skill_content = _read_skill_content(skill)
    return await svc_chat.send_message(
        session_id=session_id,
        message=prompt or f"Run skill {skill_name}.",
        user_id=user_id,
        on_progress=on_progress,
        on_stream=on_stream,
        on_stream_end=on_stream_end,
        skill_names=[skill_name],
        skill_contents={skill_name: skill_content},
    )


def _natural_language_skill_matching_enabled(svc) -> bool:
    config_service = getattr(svc, "config", None)
    if config_service is None:
        return True
    try:
        raw = config_service.read_config("console-config.json", mask=False)
        payload = json.loads(raw.get("content") or "{}")
    except Exception:
        return True
    skills_config = payload.get("skills") if isinstance(payload, dict) else None
    if not isinstance(skills_config, dict):
        return True
    return skills_config.get("natural_language_matching", True) is not False


def _register_skill_chain(
    svc,
    *,
    session_key: str,
    skill_name: str,
    prompt: str,
    matched_by: str,
    skill_match_confidence: float,
    origin_conversation_id: str = "",
    origin_turn_seq: int | None = None,
) -> tuple[str, str]:
    store = getattr(svc, "workflow_store", None)
    if store is None:
        return "", ""
    chain = store.register_chain(
        title=f"Skill: {skill_name}",
        metadata={
            "session_key": session_key,
            "skill_name": skill_name,
            "matched_by": matched_by,
            "skill_match_confidence": skill_match_confidence,
            "origin_conversation_id": origin_conversation_id,
            "origin_turn_seq": origin_turn_seq,
        },
    )
    task_id = f"skill-{chain.chain_id[:8]}"
    store.upsert_node(
        chain_id=chain.chain_id,
        task_id=task_id,
        status="running",
        node_kind="skill",
        title=skill_name,
        metadata={
            "prompt": prompt,
            "skill_name": skill_name,
            "matched_by": matched_by,
            "skill_match_confidence": skill_match_confidence,
            "origin_conversation_id": origin_conversation_id,
            "origin_turn_seq": origin_turn_seq,
        },
    )
    return chain.chain_id, task_id


def _update_skill_chain_status(svc, task_id: str, status: str) -> None:
    store = getattr(svc, "workflow_store", None)
    if store is not None and task_id:
        store.update_node_status(task_id, status)


def _build_direct_task_prompt(prompt: str, history: list[dict[str, object]]) -> str:
    if not history:
        return prompt
    lines: list[str] = []
    for item in history:
        role = str(item.get("role") or "").strip()
        content = str(item.get("content") or "").strip()
        if role and content:
            lines.append(f"{role}: {content}")
    if not lines:
        return prompt
    return (
        "Conversation context:\n"
        + "\n".join(lines)
        + "\n\nCurrent @agent request:\n"
        + prompt
    )


def _listener_message_to_payload(msg: OutboundMessage) -> dict[str, object]:
    metadata = msg.metadata or {}
    payload: dict[str, object] = {
        "type": metadata.get("event_type", "async_result"),
        "content": msg.content,
    }
    if metadata.get("tool_hint"):
        payload["tool_hint"] = True
    if "resuming" in metadata:
        payload["resuming"] = bool(metadata["resuming"])
    return payload


def _should_skip_listener_message(msg: OutboundMessage) -> bool:
    event_type = (msg.metadata or {}).get("event_type", "async_result")
    if event_type in {"complete", "stream_end"}:
        return False
    return not msg.content or msg.content in _EMPTY_LISTENER_CONTENTS

def _get_chat_service(user: UserInfo):
    from ava.console.app import get_services_for_user
    svc = get_services_for_user(user).chat
    if svc is None:
        raise HTTPException(status_code=503, detail="Chat service unavailable (gateway offline)")
    return svc

@router.get("/sessions")
async def list_sessions(user: UserInfo = Depends(auth.require_console_role_or_device_capability(console_roles=auth.READ_ROLES, device_capabilities=("read",)))):
    return _get_chat_service(user).list_sessions(user.username)

@router.post("/sessions")
async def create_session(
    body: ChatSessionCreateRequest,
    user: UserInfo = Depends(auth.require_console_role_or_device_capability(console_roles=("owner",), device_capabilities=("read",))),
):
    return _get_chat_service(user).create_session(
        user.username,
        body.title,
        participants=body.participants,
    )


@router.patch("/sessions/{session_id}")
async def update_session(
    session_id: str,
    body: ChatSessionUpdateRequest,
    user: UserInfo = Depends(auth.require_console_role_or_device_capability(console_roles=auth.EDIT_ROLES, device_capabilities=("operate",))),
):
    try:
        return _get_chat_service(user).update_session(
            session_id,
            participants=body.participants,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")


@router.post("/sessions/{session_id}/stop")
async def stop_session(
    request: Request,
    session_id: str,
    user: UserInfo = Depends(auth.require_console_role_or_device_capability(console_roles=auth.EDIT_ROLES, device_capabilities=("operate",))),
):
    svc_chat = _get_chat_service(user)
    result = await svc_chat.stop_session(session_id)

    from ava.console.app import get_services_for_user

    svc = get_services_for_user(user)
    svc.audit.log(
        user=user.username,
        role=user.role,
        action="chat.stop",
        target=session_id,
        detail={"stopped": result.get("stopped", 0)},
        ip=get_client_ip(request),
    )
    return result


@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user: UserInfo = Depends(auth.require_console_role_or_device_capability(console_roles=("owner",), device_capabilities=("read",))),
):
    if not _get_chat_service(user).delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}

@router.get("/sessions/{session_id}/history")
async def get_history(
    session_id: str,
    limit: int | None = Query(None, ge=1, le=5000),
    offset: int = Query(0, ge=0),
    user: UserInfo = Depends(auth.require_console_role_or_device_capability(console_roles=auth.READ_ROLES, device_capabilities=("read",))),
):
    return _get_chat_service(user).get_history(session_id, limit=limit, offset=offset)


@router.get("/sessions/{session_id}/context-size")
async def get_context_size(
    session_id: str,
    user: UserInfo = Depends(auth.require_console_role_or_device_capability(console_roles=auth.READ_ROLES, device_capabilities=("read",))),
):
    from fastapi.responses import JSONResponse
    try:
        data = _get_chat_service(user).get_context_size(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
    return JSONResponse(
        content=data,
        headers={
            "Deprecation": "true",
            "Sunset": "2026-08-01",
            "Link": '</api/chat/sessions/{sessionKey}/context-preview>; rel="successor-version"',
        },
    )


@router.post("/sessions/{session_id}/compress")
async def compress_context(
    session_id: str,
    user: UserInfo = Depends(auth.require_console_role_or_device_capability(console_roles=auth.EDIT_ROLES, device_capabilities=("operate",))),
):
    try:
        return _get_chat_service(user).compress_context(session_id)
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")


@router.get("/sessions/{session_id}/compressions")
async def list_context_compressions(
    session_id: str,
    user: UserInfo = Depends(auth.require_console_role_or_device_capability(console_roles=auth.READ_ROLES, device_capabilities=("read",))),
):
    return _get_chat_service(user).list_context_compressions(session_id)


@router.get("/sessions/{session_key:path}/context-preview")
async def get_context_preview(
    session_key: str,
    full: bool = Query(False, description="Return full content instead of truncated preview"),
    reveal: bool = Query(False, description="Disable redaction for preview text"),
    user: UserInfo = Depends(auth.require_console_role_or_device_capability(console_roles=auth.READ_ROLES, device_capabilities=("read",))),
):
    try:
        return _get_chat_service(user).get_context_preview(
            session_key,
            full=full,
            reveal=reveal,
        )
    except KeyError:
        raise HTTPException(status_code=404, detail="Session not found")
    except RuntimeError as exc:
        raise HTTPException(status_code=503, detail=str(exc))

@router.get("/messages")
@messages_router.get("/messages")
async def get_messages(
    session_key: str | None = Query(None, description="Session key (e.g. telegram:12345)"),
    conversation_id: str | None = Query(None, description="Conversation id within the session; omit to use active conversation"),
    trace_id: str | None = Query(None, description="Trace id to locate messages across sessions"),
    user: UserInfo = Depends(auth.require_console_role_or_device_capability(console_roles=auth.READ_ROLES, device_capabilities=("read",))),
):
    """Full message history for any session, including tool_calls and reasoning."""
    svc = _get_chat_service(user)
    if trace_id:
        return svc.get_messages_by_trace_id(trace_id)
    if not session_key:
        raise HTTPException(status_code=400, detail="session_key or trace_id is required")
    return svc.get_messages(session_key, conversation_id=conversation_id)


@router.post("/uploads")
async def upload_chat_files(
    request: Request,
    files: list[UploadFile] = File(...),
    user: UserInfo = Depends(auth.require_console_role_or_device_capability(console_roles=("owner",), device_capabilities=("operate",))),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    if len(files) > 4:
        raise HTTPException(status_code=400, detail="At most 4 files can be uploaded at once")

    from ava.console.app import get_services_for_user

    svc = get_services_for_user(user)
    uploads: list[dict[str, object]] = []
    try:
        for upload in files:
            data = await upload.read()
            uploads.append(
                svc.media.save_chat_upload(
                    filename=upload.filename,
                    mime_type=upload.content_type,
                    data=data,
                )
            )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    svc.audit.log(
        user=user.username,
        role=user.role,
        action="chat.upload",
        target="chat-input",
        detail={"count": len(uploads)},
        ip=get_client_ip(request),
    )
    return {"uploads": uploads}


@router.get("/conversations")
async def list_conversations(
    session_key: str = Query(..., description="Session key (e.g. telegram:12345)"),
    user: UserInfo = Depends(auth.require_console_role_or_device_capability(console_roles=auth.READ_ROLES, device_capabilities=("read",))),
):
    """Conversation summaries for one session_key."""
    return _get_chat_service(user).list_conversations(session_key)

@router.websocket("/ws/observe/{session_key:path}")
async def observe_ws(websocket: WebSocket, session_key: str):
    """只读 WebSocket，订阅 MessageBus observe listener 推送非 Console 会话的实时事件。"""
    user = await auth.get_ws_user(websocket)
    await websocket.accept()

    svc_chat = _get_chat_service(user)
    bus = svc_chat._agent.bus
    queue = bus.register_observe_listener(session_key)

    try:
        async def sender():
            while True:
                event = await queue.get()
                await websocket.send_text(json.dumps(event, ensure_ascii=False))

        async def receiver():
            while True:
                await websocket.receive_text()

        sender_task = asyncio.create_task(sender())
        try:
            await receiver()
        finally:
            sender_task.cancel()
    except WebSocketDisconnect:
        pass
    finally:
        bus.unregister_observe_listener(session_key, queue)
        logger.debug("Observe WS listener cleaned up for {}", session_key)


@router.websocket("/ws/{session_id}")
async def chat_ws(websocket: WebSocket, session_id: str):
    user = await auth.get_ws_user(websocket)
    if getattr(websocket.state, "device_id", None) and "operate" not in set(getattr(websocket.state, "device_capabilities", [])):
        await websocket.close(code=status.WS_1008_POLICY_VIOLATION)
        return
    await websocket.accept()

    svc_chat = _get_chat_service(user)
    from ava.console.app import get_services
    svc = get_services()

    # Register a console listener so async results (e.g. claude_code completion)
    # can be pushed to this WebSocket even when no user message is in-flight.
    session_key = f"console:{session_id}"
    bus = svc_chat._agent.bus
    listener_queue = bus.register_console_listener(session_key)

    async def _push_async_results():
        """Background task: forward outbound messages from the listener queue."""
        try:
            while True:
                msg = await listener_queue.get()
                if _should_skip_listener_message(msg):
                    continue
                payload = _listener_message_to_payload(msg)
                try:
                    await websocket.send_json(payload)
                except Exception as exc:
                    try:
                        listener_queue.put_nowait(msg)
                    except asyncio.QueueFull:
                        logger.warning(
                            "Console WS listener queue full while replaying {} for {}",
                            payload.get("type"),
                            session_id,
                        )
                    logger.debug(
                        "Console WS listener push failed for {}: {}",
                        session_id,
                        exc,
                    )
                    break
        except asyncio.CancelledError:
            pass

    push_task = asyncio.create_task(_push_async_results())

    try:
        while True:
            data = await websocket.receive_text()
            try:
                msg = json.loads(data)
                content = msg.get("content", "")
                media = msg.get("media") or []
            except json.JSONDecodeError:
                content = data
                media = []

            if not isinstance(content, str):
                content = str(content or "")
            if not isinstance(media, list):
                media = []
            media = [item for item in media if isinstance(item, str) and item]

            if not content and not media:
                continue

            svc.audit.log(
                user=user.username, role=user.role, action="chat.send",
                target=session_id, detail={"preview": content[:100], "media_count": len(media)},
            )

            async def _dispatch_listener_event(
                chunk: str,
                *,
                event_type: str,
                tool_hint: bool = False,
            ):
                metadata = {
                    "session_key": session_key,
                    "event_type": event_type,
                }
                if tool_hint:
                    metadata["tool_hint"] = True
                await bus.dispatch_to_console_listener(
                    session_key,
                    OutboundMessage(
                        channel="console",
                        chat_id=user.username,
                        content=chunk,
                        metadata=metadata,
                    ),
                )

            async def on_progress(chunk: str, *, tool_hint: bool = False, is_thinking: bool = False):
                msg_type = "thinking" if is_thinking else "progress"
                await _dispatch_listener_event(
                    chunk,
                    event_type=msg_type,
                    tool_hint=tool_hint,
                )

            async def on_stream(chunk: str):
                await _dispatch_listener_event(chunk, event_type="progress")

            async def on_stream_end(*, resuming: bool):
                metadata = {
                    "session_key": session_key,
                    "event_type": "stream_end",
                    "resuming": resuming,
                }
                await bus.dispatch_to_console_listener(
                    session_key,
                    OutboundMessage(
                        channel="console",
                        chat_id=user.username,
                        content="",
                        metadata=metadata,
                    ),
                )

            skill_trigger = _parse_skill_trigger(content) if not media else None
            if skill_trigger:
                skill_name, skill_prompt = skill_trigger
                try:
                    response = await _route_skill_trigger(
                        svc_chat=svc_chat,
                        skills_service=getattr(svc, "skills", None),
                        session_id=session_id,
                        skill_name=skill_name,
                        prompt=skill_prompt,
                        user_id=user.username,
                        on_progress=on_progress,
                        on_stream=on_stream,
                        on_stream_end=on_stream_end,
                    )
                    await _dispatch_listener_event(response, event_type="complete")
                except KeyError:
                    error = f"未注册的 skill: {skill_name}"
                    try:
                        svc_chat.record_console_message(
                            session_id,
                            role="user",
                            content=content,
                            from_agent_id="user",
                        )
                        svc_chat.record_console_message(
                            session_id,
                            role="assistant",
                            content=error,
                            from_agent_id=svc_chat.get_session_default_responder_agent_id(session_id),
                        )
                    except Exception as exc:
                        logger.debug("Failed to record missing skill response for {}: {}", session_id, exc)
                    await _dispatch_listener_event(error, event_type="complete")
                except Exception as exc:
                    logger.warning("Explicit @skill dispatch failed for {}: {}", session_id, exc)
                    await _dispatch_listener_event(f"Error: {str(exc)}", event_type="complete")
                continue

            direct_task = _extract_direct_task_mention(content) if not media else None
            if direct_task is None and not media and not content.strip().startswith("/"):
                default_responder = svc_chat.get_session_default_responder_agent_id(session_id)
                if default_responder in {"codex", "claude_code"}:
                    direct_task = (default_responder, content.strip(), [])
            if direct_task:
                task_type, prompt, mentioned_agent_ids = direct_task
                record = svc_chat.record_console_message(
                    session_id,
                    role="user",
                    content=content,
                    from_agent_id="user",
                    mentioned_agent_ids=mentioned_agent_ids,
                )
                try:
                    from ava.console.services.direct_task_service import DirectTaskService

                    agent_loop = getattr(svc_chat, "_agent", None)
                    bg_store = getattr(agent_loop, "bg_tasks", None) if agent_loop else None
                    if not agent_loop or not bg_store:
                        raise RuntimeError("Background task runtime unavailable")
                    sessions_dir = getattr(svc_chat, "_sessions_dir", None)
                    workspace_root = sessions_dir.parent if sessions_dir else Path.cwd()
                    result = await DirectTaskService(
                        agent_loop=agent_loop,
                        workspace=workspace_root,
                        bg_store=bg_store,
                        token_stats=svc.token_stats,
                        media_service=svc.media,
                        config_service=svc.config,
                    ).submit(
                        task_type=task_type,
                        prompt=_build_direct_task_prompt(prompt, svc_chat.get_history(session_id)),
                        session_key=session_key,
                        conversation_id=record["conversation_id"],
                        turn_seq=record["turn_seq"],
                        params={"mode": "standard"},
                    )
                    task_id = str(result["task_id"])
                    svc_chat.record_console_message(
                        session_id,
                        role="assistant",
                        content=(
                            f"[Background Task {task_id} QUEUED]\n"
                            f"Type: {task_type} | Duration: 0ms\n\n"
                            f"{prompt[:500]}"
                        ),
                        from_agent_id=task_type,
                    )
                    await websocket.send_json({
                        "type": "direct_task",
                        "task": {
                            "type": "direct_task",
                            "task_id": task_id,
                            "task_type": result["task_type"],
                            "session_key": session_key,
                            "prompt_preview": prompt[:200],
                            "status": result.get("status") or "queued",
                            "started_at": None,
                            "elapsed_ms": 0,
                            "result_preview": "",
                            "error_message": "",
                            "origin_conversation_id": record["conversation_id"],
                            "origin_turn_seq": record["turn_seq"],
                            "trace_id": result.get("trace_id"),
                        },
                    })
                    await _dispatch_listener_event("", event_type="complete")
                except Exception as exc:
                    logger.warning("Direct @agent dispatch failed for {}: {}", session_id, exc)
                    svc_chat.record_console_message(
                        session_id,
                        role="assistant",
                        content=f"Error: {str(exc)}",
                        from_agent_id=task_type,
                    )
                    await _dispatch_listener_event(f"Error: {str(exc)}", event_type="complete")
                continue

            if not media and not content.strip().startswith(("@", "/")):
                default_responder = svc_chat.get_session_default_responder_agent_id(session_id)
                if default_responder == "nanobot":
                    try:
                        skill_match = natural_language_skill_matching(
                            content,
                            getattr(svc.skills, "list_skills")(),
                            enabled=_natural_language_skill_matching_enabled(svc),
                        )
                    except Exception as exc:
                        logger.debug("Natural language skill matching failed for {}: {}", session_id, exc)
                        skill_match = None
                    if skill_match:
                        turn_ref = svc_chat.next_console_turn_ref(session_id)
                        chain_id, task_id = _register_skill_chain(
                            svc,
                            session_key=session_key,
                            skill_name=skill_match.skill_name,
                            prompt=content,
                            matched_by=skill_match.matched_by,
                            skill_match_confidence=skill_match.confidence,
                            origin_conversation_id=str(turn_ref["conversation_id"] or ""),
                            origin_turn_seq=turn_ref["turn_seq"],
                        )
                        if chain_id and task_id:
                            await websocket.send_json({
                                "type": "direct_task",
                                "task": {
                                    "type": "direct_task",
                                    "task_id": task_id,
                                    "task_type": "skill",
                                    "session_key": session_key,
                                    "prompt_preview": content[:200],
                                    "status": "running",
                                    "started_at": None,
                                    "elapsed_ms": 0,
                                    "result_preview": "",
                                    "error_message": "",
                                    "origin_conversation_id": turn_ref["conversation_id"],
                                    "origin_turn_seq": turn_ref["turn_seq"],
                                    "trace_id": "",
                                    "chain_id": chain_id,
                                    "node_kind": "skill",
                                    "skill_name": skill_match.skill_name,
                                    "matched_by": "natural_language",
                                },
                            })
                        await _dispatch_listener_event(
                            skill_match_narration(skill_match, content),
                            event_type="progress",
                            tool_hint=True,
                        )
                        try:
                            response = await _route_skill_trigger(
                                svc_chat=svc_chat,
                                skills_service=getattr(svc, "skills", None),
                                session_id=session_id,
                                skill_name=skill_match.skill_name,
                                prompt=content,
                                user_id=user.username,
                                on_progress=on_progress,
                                on_stream=on_stream,
                                on_stream_end=on_stream_end,
                            )
                            _update_skill_chain_status(svc, task_id, "succeeded")
                            if chain_id and task_id:
                                await websocket.send_json({
                                    "type": "direct_task",
                                    "task": {
                                        "type": "direct_task",
                                        "task_id": task_id,
                                        "task_type": "skill",
                                        "session_key": session_key,
                                        "prompt_preview": content[:200],
                                        "status": "succeeded",
                                        "started_at": None,
                                        "elapsed_ms": 0,
                                        "result_preview": response[:200],
                                        "error_message": "",
                                        "origin_conversation_id": turn_ref["conversation_id"],
                                        "origin_turn_seq": turn_ref["turn_seq"],
                                        "trace_id": "",
                                        "chain_id": chain_id,
                                        "node_kind": "skill",
                                        "skill_name": skill_match.skill_name,
                                        "matched_by": "natural_language",
                                    },
                                })
                            await _dispatch_listener_event(response, event_type="complete")
                        except Exception as exc:
                            _update_skill_chain_status(svc, task_id, "failed")
                            logger.warning("Natural language skill dispatch failed for {}: {}", session_id, exc)
                            await _dispatch_listener_event(f"Error: {str(exc)}", event_type="complete")
                        continue

            try:
                response = await svc_chat.send_message(
                    session_id=session_id,
                    message=content,
                    user_id=user.username,
                    media=media,
                    on_progress=on_progress,
                    on_stream=on_stream,
                    on_stream_end=on_stream_end,
                )
            except asyncio.CancelledError:
                task = asyncio.current_task()
                if task is not None and task.cancelling():
                    raise
                await _dispatch_listener_event("Stopped.", event_type="complete")
                continue
            await _dispatch_listener_event(response, event_type="complete")

    except WebSocketDisconnect as exc:
        logger.debug(
            "Console WS disconnected for {}: code={} reason={}",
            session_id,
            getattr(exc, "code", None),
            getattr(exc, "reason", ""),
        )
    except Exception:
        try:
            await websocket.close()
        except Exception:
            pass
    finally:
        push_task.cancel()
        bus.unregister_console_listener(session_key)
        logger.debug("Console WS listener cleaned up for {}", session_id)
