"""PageAgent routes: WebSocket 实时预览 + session 查询。"""

from __future__ import annotations

import asyncio
import json

from loguru import logger
from fastapi import APIRouter, Depends, WebSocket, WebSocketDisconnect

from ava.console import auth
from ava.console.models import UserInfo

router = APIRouter(prefix="/api/page-agent", tags=["page-agent"])


def _get_page_agent_tool():
    """从 chat service 的 agent loop 中获取已注册的 PageAgentTool 实例。"""
    from ava.console.app import get_services
    svc = get_services()
    if not svc.chat:
        return None
    agent = svc.chat._agent
    if not agent or not hasattr(agent, "tools"):
        return None
    # tools 是 ToolRegistry，按名称查找
    return agent.tools.get("page_agent")


@router.get("/sessions")
async def list_sessions(user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer"))):
    """返回当前活跃的 page-agent session 列表。"""
    tool = _get_page_agent_tool()
    if not tool:
        return {"sessions": []}
    return {"sessions": await tool.list_sessions()}


@router.post("/restart-runner")
async def restart_runner(user: UserInfo = Depends(auth.require_role("admin", "editor", "viewer"))):
    """停止 page-agent runner 进程，下次调用时自动重启。"""
    tool = _get_page_agent_tool()
    if not tool:
        return {"success": False, "message": "PageAgent tool not available"}
    msg = await tool._do_restart_runner()
    return {"success": True, "message": msg}


@router.websocket("/ws/{session_id}")
async def page_agent_ws(websocket: WebSocket, session_id: str):
    """WebSocket 端点：实时转发 screencast 帧和 activity 事件。"""
    user = await auth.get_ws_user(websocket)
    if user.role == "mock_tester":
        await websocket.close(code=1008)
        return
    await websocket.accept()

    tool = _get_page_agent_tool()
    if not tool:
        await websocket.close(code=1011, reason="PageAgent tool not available")
        return

    # 消息队列：runner 推送的事件放入队列，WS 循环取出发送
    queue: asyncio.Queue = asyncio.Queue(maxsize=100)

    def on_event(msg: dict):
        try:
            queue.put_nowait(msg)
        except asyncio.QueueFull:
            pass  # 丢弃旧帧，保持实时性

    # 订阅事件
    tool.subscribe(session_id, on_event)

    # 启动 screencast
    try:
        await tool.start_screencast(session_id)
    except Exception as e:
        logger.warning("page_agent ws: failed to start screencast: {}", e)
        # screencast 启动失败不阻断连接，activity 事件仍然可以传输

    try:
        page_info = await tool.get_page_info(session_id)
        if page_info.get("success"):
            await websocket.send_text(json.dumps({
                "type": "page_info",
                "session_id": session_id,
                **page_info.get("result", {}),
            }, ensure_ascii=False))
    except Exception as e:
        logger.debug("page_agent ws: failed to fetch page info: {}", e)

    async def _sender():
        """从队列取事件发给 WS 客户端。"""
        try:
            while True:
                msg = await queue.get()
                # frame 事件中 data 已经是 base64，直接转发
                await websocket.send_text(json.dumps(msg, ensure_ascii=False))
        except (asyncio.CancelledError, WebSocketDisconnect):
            pass
        except Exception:
            pass

    async def _receiver():
        """接收客户端消息（目前只用于保持连接活跃）。"""
        try:
            while True:
                await websocket.receive_text()
        except (WebSocketDisconnect, Exception):
            pass

    sender_task = asyncio.create_task(_sender())
    try:
        await _receiver()
    finally:
        sender_task.cancel()
        tool.unsubscribe(session_id, on_event)
        try:
            await tool.stop_screencast(session_id)
        except Exception:
            pass
