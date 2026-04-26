"""Chat routes: WebSocket conversations + session management."""

from __future__ import annotations

import asyncio
import json

from loguru import logger
from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile, WebSocket, WebSocketDisconnect
from nanobot.bus.events import OutboundMessage

from ava.console import auth
from ava.console.middleware import get_client_ip
from ava.console.models import ChatSessionCreateRequest, UserInfo

router = APIRouter(prefix="/api/chat", tags=["chat"])

_EMPTY_LISTENER_CONTENTS = {"(empty)", "[empty message]"}


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
async def list_sessions(user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester"))):
    return _get_chat_service(user).list_sessions(user.username)

@router.post("/sessions")
async def create_session(
    body: ChatSessionCreateRequest,
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    return _get_chat_service(user).create_session(user.username, body.title)

@router.delete("/sessions/{session_id}")
async def delete_session(
    session_id: str,
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    if not _get_chat_service(user).delete_session(session_id):
        raise HTTPException(status_code=404, detail="Session not found")
    return {"ok": True}

@router.get("/sessions/{session_id}/history")
async def get_history(
    session_id: str,
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    return _get_chat_service(user).get_history(session_id)


@router.get("/sessions/{session_key:path}/context-preview")
async def get_context_preview(
    session_key: str,
    full: bool = Query(False, description="Return full content instead of truncated preview"),
    reveal: bool = Query(False, description="Disable redaction for preview text"),
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
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
async def get_messages(
    session_key: str = Query(..., description="Session key (e.g. telegram:12345)"),
    conversation_id: str | None = Query(None, description="Conversation id within the session; omit to use active conversation"),
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    """Full message history for any session, including tool_calls and reasoning."""
    return _get_chat_service(user).get_messages(session_key, conversation_id=conversation_id)


@router.post("/uploads")
async def upload_chat_images(
    request: Request,
    files: list[UploadFile] = File(...),
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    if not files:
        raise HTTPException(status_code=400, detail="No files uploaded")
    if len(files) > 4:
        raise HTTPException(status_code=400, detail="At most 4 images can be uploaded at once")

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
    user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer", "mock_tester")),
):
    """Conversation summaries for one session_key."""
    return _get_chat_service(user).list_conversations(session_key)

@router.websocket("/ws/observe/{session_key:path}")
async def observe_ws(websocket: WebSocket, session_key: str):
    """只读 WebSocket，订阅 MessageBus observe listener 推送非 Console 会话的实时事件。"""
    user = await auth.get_ws_user(websocket)
    if user.role == "mock_tester":
        await websocket.accept()
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
        return
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
    if user.role == "mock_tester":
        await websocket.accept()
        try:
            while True:
                await websocket.receive_text()
        except WebSocketDisconnect:
            pass
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

            response = await svc_chat.send_message(
                session_id=session_id,
                message=content,
                user_id=user.username,
                media=media,
                on_progress=on_progress,
                on_stream=on_stream,
                on_stream_end=on_stream_end,
            )
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
