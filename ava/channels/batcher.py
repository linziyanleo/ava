"""Reusable time-based message debounce buffer for chat channels."""

from __future__ import annotations

import asyncio
from typing import Any, Awaitable, Callable

from loguru import logger


class MessageBatcher:
    """
    Groups messages by key (e.g. chat_id) and flushes after a configurable
    quiet period.  Each new message resets the timer for that key.

    When the timer expires, all buffered content and media are merged and
    forwarded via *flush_callback* in a single call.
    """

    def __init__(
        self,
        timeout_s: float,
        flush_callback: Callable[..., Awaitable[None]],
        *,
        on_first_message: Callable[[str], None] | None = None,
    ):
        """
        Args:
            timeout_s: Seconds to wait after the last message before flushing.
            flush_callback: ``async def(sender_id, chat_id, content, media, metadata, session_key)``
            on_first_message: Optional sync callback(chat_id) fired when a buffer is first created
                              (e.g. to start a typing indicator).
        """
        self._timeout = timeout_s
        self._flush_cb = flush_callback
        self._on_first = on_first_message
        self._buffers: dict[str, _Buffer] = {}
        self._tasks: dict[str, asyncio.Task] = {}

    async def add(
        self,
        key: str,
        content: str,
        media: list[str],
        sender_id: str,
        chat_id: str,
        metadata: dict[str, Any],
        session_key: str | None = None,
    ) -> None:
        """Append a message to the buffer for *key* and (re)start the flush timer."""
        if key not in self._buffers:
            self._buffers[key] = _Buffer(
                sender_id=sender_id,
                chat_id=chat_id,
                session_key=session_key,
            )
            if self._on_first:
                self._on_first(chat_id)

        buf = self._buffers[key]
        if content and content != "[empty message]":
            buf.contents.append(content)
        buf.media.extend(media)
        buf.metadata = metadata  # always keep the latest

        old_task = self._tasks.pop(key, None)
        if old_task and not old_task.done():
            old_task.cancel()
        self._tasks[key] = asyncio.create_task(self._delayed_flush(key))

    async def _delayed_flush(self, key: str) -> None:
        try:
            await asyncio.sleep(self._timeout)
            await self._do_flush(key)
        except asyncio.CancelledError:
            pass

    async def _do_flush(self, key: str) -> None:
        buf = self._buffers.pop(key, None)
        self._tasks.pop(key, None)
        if buf is None:
            return

        content = "\n".join(buf.contents) if buf.contents else "[empty message]"
        media = list(dict.fromkeys(buf.media))  # dedupe, preserve order

        logger.debug(
            "MessageBatcher flush [{}]: {} chars, {} media",
            key, len(content), len(media),
        )

        await self._flush_cb(
            sender_id=buf.sender_id,
            chat_id=buf.chat_id,
            content=content,
            media=media,
            metadata=buf.metadata,
            session_key=buf.session_key,
        )

    async def cancel_all(self) -> None:
        """Cancel every pending flush (call on shutdown)."""
        for task in self._tasks.values():
            if not task.done():
                task.cancel()
        self._tasks.clear()
        self._buffers.clear()


class _Buffer:
    __slots__ = ("sender_id", "chat_id", "session_key", "contents", "media", "metadata")

    def __init__(self, sender_id: str, chat_id: str, session_key: str | None):
        self.sender_id = sender_id
        self.chat_id = chat_id
        self.session_key = session_key
        self.contents: list[str] = []
        self.media: list[str] = []
        self.metadata: dict[str, Any] = {}
