"""Per-tab DevTools event cache for the browser substrate (AVA-58).

Decisions (see task spec §0 Resolved Q1/Q2):

* Cache key is the caller-provided ``tab_key`` (typically
  ``f"{mcp_server}:{active_tab_index}"`` captured at snapshot time).
* Each ``(tab_key, event_type)`` has its own monotonic ``seq`` and a bounded
  ``deque`` ring buffer.
* ``mark_action_boundary`` records the current ``next_seq`` per event_type;
  ``query(since="last_action")`` returns events with ``seq >= last_action_seq``.
* ``query(since="<cursor>")`` accepts the cursor returned by a previous query
  (an integer-as-string) and returns events with ``seq >= int(cursor)``.

This module has no MCP / Playwright dependency; it is exercised entirely with
``append``/``mark_action_boundary``/``query`` from unit tests.
"""

from __future__ import annotations

from collections import deque
from dataclasses import dataclass, field
from typing import Any, Literal, Mapping

EventType = Literal["network", "console", "errors"]
_EVENT_TYPES: tuple[EventType, ...] = ("network", "console", "errors")


@dataclass(frozen=True)
class CachedEvent:
    """A single DevTools event row in the cache."""

    seq: int
    type: EventType
    payload: Mapping[str, Any]


@dataclass
class _TabBuffers:
    network: deque[CachedEvent]
    console: deque[CachedEvent]
    errors: deque[CachedEvent]
    last_action_seq: dict[str, int] = field(default_factory=dict)
    next_seq: dict[str, int] = field(default_factory=dict)


class TabEventCache:
    """Bounded per-tab event store with action-boundary cursor semantics."""

    def __init__(
        self,
        *,
        network_max: int,
        console_max: int,
        errors_max: int,
    ) -> None:
        if network_max <= 0 or console_max <= 0 or errors_max <= 0:
            raise ValueError("event cache caps must be positive")
        self._caps: dict[str, int] = {
            "network": network_max,
            "console": console_max,
            "errors": errors_max,
        }
        self._tabs: dict[str, _TabBuffers] = {}

    # ----- structural helpers -----------------------------------------

    def _ensure_tab(self, tab_key: str) -> _TabBuffers:
        buf = self._tabs.get(tab_key)
        if buf is None:
            buf = _TabBuffers(
                network=deque(maxlen=self._caps["network"]),
                console=deque(maxlen=self._caps["console"]),
                errors=deque(maxlen=self._caps["errors"]),
                last_action_seq={t: 0 for t in _EVENT_TYPES},
                next_seq={t: 0 for t in _EVENT_TYPES},
            )
            self._tabs[tab_key] = buf
        return buf

    @staticmethod
    def _bucket(buf: _TabBuffers, event_type: EventType) -> deque[CachedEvent]:
        return getattr(buf, event_type)

    # ----- write side --------------------------------------------------

    def append(
        self,
        tab_key: str,
        event_type: EventType,
        payload: Mapping[str, Any],
    ) -> int:
        """Append ``payload`` and return the assigned monotonic ``seq``."""
        if event_type not in _EVENT_TYPES:
            raise ValueError(f"unknown event_type: {event_type!r}")
        buf = self._ensure_tab(tab_key)
        seq = buf.next_seq[event_type]
        buf.next_seq[event_type] = seq + 1
        bucket = self._bucket(buf, event_type)
        bucket.append(CachedEvent(seq=seq, type=event_type, payload=dict(payload)))
        return seq

    def mark_action_boundary(self, tab_key: str) -> None:
        """Snapshot ``next_seq`` so subsequent ``since='last_action'`` queries
        return only events appended after this call."""
        buf = self._ensure_tab(tab_key)
        for et in _EVENT_TYPES:
            buf.last_action_seq[et] = buf.next_seq[et]

    def clear_tab(self, tab_key: str) -> None:
        """Drop all cached state for ``tab_key`` (e.g. on tab close)."""
        self._tabs.pop(tab_key, None)

    # ----- read side ---------------------------------------------------

    def query(
        self,
        tab_key: str,
        event_type: EventType,
        *,
        since: str = "last_action",
        url_contains: str | None = None,
        method: str | None = None,
        status: int | None = None,
        level: str | None = None,
        text_contains: str | None = None,
        limit: int | None = None,
    ) -> dict[str, Any]:
        """Return cached events matching ``since`` + optional filters.

        Returns ``{"events": [...], "next_cursor": "<int>", "truncated": bool}``.
        ``next_cursor`` is the string form of the next ``seq`` to fetch.
        """
        if event_type not in _EVENT_TYPES:
            raise ValueError(f"unknown event_type: {event_type!r}")
        if tab_key not in self._tabs:
            return {"events": [], "next_cursor": "0", "truncated": False}

        buf = self._tabs[tab_key]
        bucket = self._bucket(buf, event_type)

        if since == "last_action":
            min_seq = buf.last_action_seq[event_type]
        else:
            try:
                min_seq = int(since)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"since must be 'last_action' or an integer cursor string, got {since!r}"
                ) from exc
            if min_seq < 0:
                raise ValueError("cursor must be non-negative")

        method_norm = method.upper() if method else None
        level_norm = level.lower() if level else None

        out: list[dict[str, Any]] = []
        for ev in bucket:
            if ev.seq < min_seq:
                continue
            payload = ev.payload
            if url_contains and url_contains not in str(payload.get("url", "")):
                continue
            if method_norm and str(payload.get("method", "")).upper() != method_norm:
                continue
            if status is not None and payload.get("status") != status:
                continue
            if level_norm and str(payload.get("level", "")).lower() != level_norm:
                continue
            if text_contains and text_contains not in str(payload.get("text", "")):
                continue
            out.append({"seq": ev.seq, "type": ev.type, **payload})

        truncated = False
        if limit is not None and limit >= 0 and len(out) > limit:
            out = out[:limit]
            truncated = True

        next_cursor = str(buf.next_seq[event_type])
        return {"events": out, "next_cursor": next_cursor, "truncated": truncated}

    # ----- introspection ------------------------------------------------

    def known_tabs(self) -> tuple[str, ...]:
        return tuple(self._tabs)

    def caps(self) -> Mapping[str, int]:
        return dict(self._caps)
