"""Patch to add Console WebSocket listener support to MessageBus.

Adds two sets of methods to MessageBus:

Console listeners (OutboundMessage, 覆盖式注册, 用于 Console WS 双向会话):
  - register_console_listener(session_key) -> asyncio.Queue
  - unregister_console_listener(session_key)
  - dispatch_to_console_listener(session_key, msg)

Observe listeners (dict 生命周期事件, 追加式注册, 用于非 Console 会话只读订阅):
  - register_observe_listener(session_key) -> asyncio.Queue
  - unregister_observe_listener(session_key, queue)
  - dispatch_observe_event(session_key, event)
"""

from __future__ import annotations

import asyncio

from loguru import logger
from nanobot.bus.events import OutboundMessage

from ava.launcher import register_patch


def apply_bus_patch() -> str:
    from nanobot.bus.queue import MessageBus

    if not hasattr(MessageBus, "publish_outbound"):
        logger.warning("bus_patch skipped: MessageBus.publish_outbound not found")
        return "bus_patch skipped (publish_outbound not found)"

    if getattr(MessageBus.publish_outbound, "_ava_bus_patched", False):
        return "bus_patch already applied (skipped)"

    # --- register_console_listener ---
    def register_console_listener(self: MessageBus, session_key: str) -> asyncio.Queue:
        """Register a queue-based listener for console WebSocket events on a session.

        Returns an asyncio.Queue that receives OutboundMessage objects.
        Replaces any existing listener for the same session_key.
        """
        if not hasattr(self, "_console_listeners"):
            self._console_listeners: dict[str, asyncio.Queue] = {}
        queue: asyncio.Queue = asyncio.Queue(maxsize=256)
        self._console_listeners[session_key] = queue
        return queue

    # --- unregister_console_listener ---
    def unregister_console_listener(self: MessageBus, session_key: str) -> None:
        """Remove the console listener queue for a session."""
        listeners = getattr(self, "_console_listeners", {})
        listeners.pop(session_key, None)

    # --- dispatch_to_console_listener ---
    async def dispatch_to_console_listener(
        self: MessageBus, session_key: str, msg: OutboundMessage
    ) -> None:
        """Put an OutboundMessage into the registered console listener queue."""
        listeners = getattr(self, "_console_listeners", {})
        queue = listeners.get(session_key)
        if queue is None:
            return
        try:
            queue.put_nowait(msg)
        except asyncio.QueueFull:
            logger.warning("Console listener queue full for session {}, dropping message", session_key)
        except Exception as exc:
            logger.warning("Console listener dispatch error for session {}: {}", session_key, exc)
            listeners.pop(session_key, None)

    # --- patch publish_outbound to route console messages to registered queues ---
    original_publish_outbound = MessageBus.publish_outbound

    async def patched_publish_outbound(self: MessageBus, msg: OutboundMessage) -> None:
        """Intercept outbound messages: route console-channel messages to listener queues."""
        # Always put into the main outbound queue (ChannelManager consumes it)
        await original_publish_outbound(self, msg)

        # Also route to console listener if registered
        listeners = getattr(self, "_console_listeners", {})
        if not listeners:
            return

        # Derive the session key from the message
        # console messages use channel='console' and chat_id=user_id
        # async results from background tasks have session_key in metadata
        meta = msg.metadata or {}
        session_key = meta.get("session_key") or (
            f"{msg.channel}:{msg.chat_id}" if msg.channel == "console" else None
        )
        if session_key and session_key in listeners:
            queue = listeners[session_key]
            try:
                queue.put_nowait(msg)
            except asyncio.QueueFull:
                logger.warning("Console listener queue full for {}, dropping", session_key)

    patched_publish_outbound._ava_bus_patched = True
    MessageBus.publish_outbound = patched_publish_outbound

    MessageBus.register_console_listener = register_console_listener
    MessageBus.unregister_console_listener = unregister_console_listener
    MessageBus.dispatch_to_console_listener = dispatch_to_console_listener

    # --- observe listener（生命周期事件，追加式注册，支持多 WS 同时观察同一 session）---
    def register_observe_listener(self: MessageBus, session_key: str) -> asyncio.Queue:
        """注册 observe listener queue，接收 dict 生命周期事件。"""
        if not hasattr(self, "_observe_listeners"):
            self._observe_listeners: dict[str, list[asyncio.Queue]] = {}
        queue: asyncio.Queue = asyncio.Queue(maxsize=200)
        self._observe_listeners.setdefault(session_key, []).append(queue)
        return queue

    def unregister_observe_listener(self: MessageBus, session_key: str, queue: asyncio.Queue) -> None:
        """移除指定的 observe listener queue。"""
        listeners = getattr(self, "_observe_listeners", {})
        if session_key in listeners:
            try:
                listeners[session_key].remove(queue)
            except ValueError:
                pass
            if not listeners[session_key]:
                del listeners[session_key]

    def dispatch_observe_event(self: MessageBus, session_key: str, event: dict) -> None:
        """向指定 session_key 的所有 observe listener 广播生命周期事件。"""
        listeners = getattr(self, "_observe_listeners", {})
        for queue in listeners.get(session_key, []):
            try:
                queue.put_nowait(event)
            except asyncio.QueueFull:
                logger.warning("Observe listener queue full for {}, dropping event", session_key)

    MessageBus.register_observe_listener = register_observe_listener
    MessageBus.unregister_observe_listener = unregister_observe_listener
    MessageBus.dispatch_observe_event = dispatch_observe_event

    return "MessageBus patched with console + observe listeners"


register_patch("bus_console_listener", apply_bus_patch)
