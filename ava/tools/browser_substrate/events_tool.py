"""``browser_events`` — incremental DevTools query (AVA-58).

Single tool with ``event_type`` enum (``network`` / ``console`` / ``errors``).
v1 surfaces the substrate's per-tab cache; events are populated by
substrate-mediated actions (most commonly :class:`BrowserFetchTool`). Events
originating purely from page navigations / user clicks are a v2 gap — for now
fall back to ``mcp_playwright_daily_browser_network_requests`` directly.

Cursor semantics (task spec §0 Q2):
* ``since="last_action"`` — events with ``seq >= cache.last_action_seq[type]``
* ``since="<int>"`` — events with ``seq >= int(since)``
"""

from __future__ import annotations

import json
from typing import Any

from nanobot.agent.tools.base import Tool

from ava.tools.browser_substrate.client import BrowserSubstrateClient
from ava.tools.browser_substrate.event_cache import EventType


_VALID_EVENT_TYPES: tuple[EventType, ...] = ("network", "console", "errors")


class BrowserEventsTool(Tool):
    """Query the substrate's per-tab event cache."""

    def __init__(self, *, client: BrowserSubstrateClient) -> None:
        self._client = client

    @property
    def name(self) -> str:
        return "browser_events"

    @property
    def description(self) -> str:
        return (
            "Query DevTools incremental evidence captured by the substrate. "
            "`event_type` selects 'network' | 'console' | 'errors'. `since` is "
            "either 'last_action' (default — events after the most recent "
            "substrate action) or a string-cursor returned by a previous call. "
            "Returns events recorded by substrate-mediated tools; for raw "
            "Playwright DevTools dumps, call mcp_playwright_daily_browser_* "
            "directly."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "event_type": {
                    "type": "string",
                    "enum": list(_VALID_EVENT_TYPES),
                    "description": "Which event surface to query.",
                },
                "since": {
                    "type": "string",
                    "description": "'last_action' or an integer-string cursor.",
                },
                "url_contains": {
                    "type": "string",
                    "description": "Filter network events by substring of `url`.",
                },
                "method": {
                    "type": "string",
                    "description": "Filter network events by HTTP method.",
                },
                "status": {
                    "type": "integer",
                    "description": "Filter network events by HTTP status code.",
                },
                "level": {
                    "type": "string",
                    "description": "Filter console events by level.",
                },
                "text_contains": {
                    "type": "string",
                    "description": "Filter console/errors events by substring of `text`.",
                },
                "limit": {
                    "type": "integer",
                    "description": "Cap returned events.",
                },
            },
            "required": ["event_type"],
        }

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:  # type: ignore[override]
        event_type = kwargs.get("event_type")
        if event_type not in _VALID_EVENT_TYPES:
            return json.dumps(
                {
                    "ok": False,
                    "error": f"event_type must be one of {list(_VALID_EVENT_TYPES)}",
                }
            )
        tab_key = f"{self._client.mcp_server_name}:active"
        cache = self._client.cache()
        try:
            result = cache.query(
                tab_key,
                event_type,  # type: ignore[arg-type]
                since=str(kwargs.get("since", "last_action")),
                url_contains=kwargs.get("url_contains"),
                method=kwargs.get("method"),
                status=kwargs.get("status"),
                level=kwargs.get("level"),
                text_contains=kwargs.get("text_contains"),
                limit=kwargs.get("limit"),
            )
        except ValueError as exc:
            return json.dumps({"ok": False, "error": str(exc)})
        return json.dumps({"ok": True, "event_type": event_type, **result})
