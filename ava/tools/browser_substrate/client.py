"""BrowserSubstrateClient — facade over the daily-Chrome MCP server.

Owns:

* The MCP tool-name resolution (``mcp_{server}_{raw}``).
* The per-tab :class:`TabEventCache`.
* The action-boundary protocol described in task spec §0 Q2: each call to
  ``run_action_then_pull_events`` snapshots ``browser_network_requests`` /
  ``browser_console_messages`` and ingests new rows into the cache, then marks
  an action boundary so subsequent ``since="last_action"`` queries are scoped
  to the next action.

This module makes no assumptions about the *shape* of the MCP response text;
parsers live next to the tool that consumes them. The skeleton here is what
``BrowserFetchTool``, ``BrowserEventsTool``, and the adapter runner all share.
"""

from __future__ import annotations

import re
from typing import Any, Awaitable, Callable, Mapping, Protocol

from ava.tools.browser_substrate.event_cache import EventType, TabEventCache

_MCP_NAME_SANITIZE_RE = re.compile(r"_+")


class _RegistryLike(Protocol):
    """Subset of nanobot ToolRegistry the substrate consumes."""

    def has(self, name: str) -> bool: ...
    async def execute(self, name: str, params: Mapping[str, Any]) -> Any: ...


class SubstrateError(Exception):
    """Raised when the substrate cannot satisfy a precondition."""


class MCPToolMissing(SubstrateError):
    """Raised when the configured MCP server has not registered a needed tool."""


class BrowserSubstrateClient:
    """Per-loop facade. Construct once at tool-registration time."""

    def __init__(
        self,
        *,
        mcp_server_name: str,
        tool_registry: _RegistryLike | None,
        event_cache: TabEventCache,
    ) -> None:
        self._mcp_server_name = self._sanitize(mcp_server_name)
        self._registry = tool_registry
        self._cache = event_cache

    # ----- naming ------------------------------------------------------

    @staticmethod
    def _sanitize(raw: str) -> str:
        cleaned = re.sub(r"[^a-zA-Z0-9_-]", "_", str(raw or ""))
        return _MCP_NAME_SANITIZE_RE.sub("_", cleaned)

    @property
    def mcp_server_name(self) -> str:
        return self._mcp_server_name

    def mcp_tool_name(self, raw: str) -> str:
        return f"mcp_{self._mcp_server_name}_{raw}"

    # ----- MCP plumbing ------------------------------------------------

    async def call_mcp(self, raw_tool_name: str, params: Mapping[str, Any]) -> str:
        """Invoke ``mcp_{server}_{raw_tool_name}`` and return the textual result.

        Raises :class:`MCPToolMissing` when the registry has no such tool, or
        :class:`SubstrateError` when no registry is wired (offline tests).
        """
        if self._registry is None:
            raise SubstrateError(
                "BrowserSubstrateClient was constructed without a tool registry"
            )
        tool_name = self.mcp_tool_name(raw_tool_name)
        has = getattr(self._registry, "has", None)
        if callable(has) and not has(tool_name):
            raise MCPToolMissing(
                f"MCP tool '{tool_name}' is not registered; configure "
                f"tools.mcpServers.{self._mcp_server_name} and restart."
            )
        result = await self._registry.execute(tool_name, dict(params))
        if isinstance(result, str):
            return result
        # nanobot wrappers usually return strings; serialise dict-ish results
        # defensively rather than guessing schema here.
        return str(result)

    # ----- cache passthroughs -----------------------------------------

    def cache(self) -> TabEventCache:
        return self._cache

    def append_event(
        self,
        tab_key: str,
        event_type: EventType,
        payload: Mapping[str, Any],
    ) -> int:
        return self._cache.append(tab_key, event_type, payload)

    def mark_action_boundary(self, tab_key: str) -> None:
        self._cache.mark_action_boundary(tab_key)

    def clear_tab(self, tab_key: str) -> None:
        self._cache.clear_tab(tab_key)

    # ----- helpers used by fetch/events tools (filled in subsequent steps)

    async def with_active_tab(
        self,
        action: Callable[[str], Awaitable[Any]],
    ) -> Any:
        """Resolve the current active-tab key (per Q1 active-tab-only model)
        and call ``action(tab_key)``. The tab key returned for v1 is
        ``f"{server}:active"``; multi-tab callers must explicitly select via
        ``mcp_{server}_browser_tabs(action='select', index=...)`` first.
        """
        tab_key = f"{self._mcp_server_name}:active"
        return await action(tab_key)
