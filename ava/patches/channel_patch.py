"""Channel extensions patch for TelegramChannel message batching and send_delta fixes.

Intercept: TelegramChannel.send
Behavior: Messages are queued in a MessageBatcher; within a 1-second window,
multiple messages to the same chat_id are merged into a single send.

Intercept: TelegramChannel.send_delta
Behavior: (a) Always stop typing on stream_end regardless of buf state —
upstream skips _stop_typing when buf is empty (tool-call-only turns).
(b) Fallback to send_message when buf.message_id is None at stream_end —
upstream drops the message; we send a fresh one instead.
Stream_id matching and not_modified handling are left to upstream (since 33abe915).

Note: Voice transcription uses upstream Groq Whisper (config: providers.groq.apiKey).
Session backfill is handled by storage_patch (after SQLite load).
"""

from __future__ import annotations

from typing import Any

from loguru import logger

from ava.channels.batcher import MessageBatcher
from ava.launcher import register_patch


def apply_channel_patch() -> str:
    """
    Patch TelegramChannel to add message batching and send_delta fixes.

    Returns:
        Description of what was patched.
    """
    from nanobot.channels.telegram import TelegramChannel

    missing = [
        method_name
        for method_name in ("__init__", "send", "send_delta")
        if not hasattr(TelegramChannel, method_name)
    ]
    if missing:
        logger.warning(
            "channel_patch skipped: TelegramChannel missing methods {}",
            ", ".join(missing),
        )
        return f"channel_patch skipped (missing methods: {', '.join(missing)})"

    if (
        getattr(TelegramChannel.__init__, "_ava_channel_patched", False)
        or getattr(TelegramChannel.send, "_ava_channel_patched", False)
        or getattr(TelegramChannel.send_delta, "_ava_channel_patched", False)
    ):
        return "channel_patch already applied (skipped)"

    # ------------------------------------------------------------------
    # 1. Patch __init__: normalize foreign Pydantic config objects back into
    #    TelegramChannel's own schema before upstream accesses new fields.
    # ------------------------------------------------------------------
    original_init = TelegramChannel.__init__

    def patched_init(self: TelegramChannel, config: Any, bus: Any) -> None:
        if not isinstance(config, dict) and hasattr(config, "model_dump"):
            config = config.model_dump(mode="json", by_alias=True)
        original_init(self, config, bus)

    patched_init._ava_channel_patched = True
    TelegramChannel.__init__ = patched_init

    # ------------------------------------------------------------------
    # 2. Patch send: message batching
    # ------------------------------------------------------------------
    original_send = TelegramChannel.send

    batcher: MessageBatcher | None = None

    async def batched_send_callback(
        sender_id: str,
        chat_id: str,
        content: str,
        media: list[str],
        metadata: dict[str, Any],
        session_key: str | None = None,
    ) -> None:
        """Batch callback that sends merged messages via original send."""
        from nanobot.bus.events import OutboundMessage

        msg = OutboundMessage(
            channel="telegram",
            chat_id=chat_id,
            content=content,
            media=media,
            metadata=metadata,
        )
        instance = _channel_instance.get("ref")
        if instance is not None:
            await original_send(instance, msg)

    _channel_instance: dict = {}

    async def patched_send(self: TelegramChannel, msg: Any) -> None:
        """Intercept send to add batching logic."""
        nonlocal batcher

        _channel_instance["ref"] = self

        if batcher is None:
            batcher = MessageBatcher(
                timeout_s=1.0,
                flush_callback=batched_send_callback,
            )

        await batcher.add(
            key=str(msg.chat_id),
            content=msg.content,
            media=getattr(msg, "media", None) or [],
            sender_id=getattr(msg, "sender_id", ""),
            chat_id=msg.chat_id,
            metadata=getattr(msg, "metadata", None) or {},
            session_key=None,
        )

    patched_send._ava_channel_patched = True
    TelegramChannel.send = patched_send

    # ------------------------------------------------------------------
    # 3. Patch send_delta: two behaviors upstream doesn't cover:
    #    (a) Always stop typing on stream_end regardless of buf state —
    #        upstream only calls _stop_typing after it confirms buf has text,
    #        leaving the typing indicator stuck on tool-call-only turns.
    #    (b) Fallback send_message when buf.message_id is None on stream_end —
    #        upstream returns early and drops the message; we send a fresh one.
    #    All other logic (stream_id matching, not_modified handling) is now
    #    handled by upstream send_delta (since 33abe915).
    # ------------------------------------------------------------------
    original_send_delta = TelegramChannel.send_delta

    async def patched_send_delta(self: TelegramChannel, chat_id: str, delta: str, metadata: dict | None = None) -> None:
        meta = metadata or {}
        if meta.get("_stream_end"):
            # (a) Stop typing immediately — upstream skips this when buf is empty
            self._stop_typing(chat_id)

            buf = self._stream_bufs.get(chat_id)
            if buf and buf.text and buf.message_id is None:
                # (b) send_message hasn't completed yet: send a fresh message
                stream_id = meta.get("_stream_id")
                if stream_id is not None and buf.stream_id is not None and buf.stream_id != stream_id:
                    self._stream_bufs.pop(chat_id, None)
                    return
                try:
                    from nanobot.utils.helpers import strip_think
                    text = strip_think(buf.text) or buf.text
                except Exception:
                    text = buf.text
                self._stream_bufs.pop(chat_id, None)
                logger.info("send_delta fallback send_message chat={} len={}", chat_id, len(text))
                try:
                    await self._call_with_retry(self._app.bot.send_message, chat_id=int(chat_id), text=text)
                except Exception as exc:
                    logger.warning("send_delta fallback send failed: {}", exc)
                return

        await original_send_delta(self, chat_id, delta, metadata)

    patched_send_delta._ava_channel_patched = True
    TelegramChannel.send_delta = patched_send_delta

    # ------------------------------------------------------------------
    # 4. Patch start: add CommandHandlers for sidecar slash commands
    #    (/task, /task_cancel, /cc_status) so Telegram doesn't swallow them
    #    (upstream MessageHandler uses ~filters.COMMAND which excludes /).
    # ------------------------------------------------------------------
    original_start = TelegramChannel.start

    async def patched_start(self: TelegramChannel) -> None:
        await original_start(self)
        if not hasattr(self, "_app") or not self._app:
            return
        try:
            from telegram import BotCommand
            from telegram.ext import CommandHandler

            for cmd_name in ("task", "task_cancel", "cc_status"):
                self._app.add_handler(CommandHandler(cmd_name, self._forward_command))

            existing = list(self.BOT_COMMANDS)
            extra = [
                BotCommand("task", "Show background task status"),
                BotCommand("task_cancel", "Cancel a background task"),
                BotCommand("cc_status", "Show task status (alias)"),
            ]
            await self._app.bot.set_my_commands(existing + extra)
            logger.info("channel_patch: registered /task /task_cancel /cc_status handlers")
        except Exception as exc:
            logger.warning("channel_patch: failed to register sidecar commands: {}", exc)

    patched_start._ava_channel_patched = True
    TelegramChannel.start = patched_start

    return "TelegramChannel patched: config normalization + message batching + send_delta typing fix + sidecar command handlers"


register_patch("channel_extensions", apply_channel_patch)
