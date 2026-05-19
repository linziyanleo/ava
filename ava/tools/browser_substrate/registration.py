"""Browser substrate registration helper (AVA-58, plan §F step 8).

This module wires the substrate tools onto an :class:`AgentLoop`-like object
according to ``tools.browser_substrate`` config. It is the single seam between
the substrate package and ``ava.patches.tools_patch``.

Q7 contract:
* ``enabled=False`` (default) → returns ``False`` without registering anything.
* ``enabled=True`` but ``tools.mcpServers[mcp_server]`` is missing → raises
  :class:`SubstrateConfigurationError` (fail-fast at startup).
* ``enabled=True`` and configured → registers all five tools and returns ``True``.
"""

from __future__ import annotations

from typing import Any

from ava.tools.browser_substrate.adapter_registry import SiteAdapterRegistry
from ava.tools.browser_substrate.adapter_tools import (
    SiteAdapterInfoTool,
    SiteAdapterListTool,
    SiteAdapterRunTool,
)
from ava.tools.browser_substrate.client import BrowserSubstrateClient
from ava.tools.browser_substrate.event_cache import TabEventCache
from ava.tools.browser_substrate.events_tool import BrowserEventsTool
from ava.tools.browser_substrate.fetch_tool import BrowserFetchTool


class SubstrateConfigurationError(RuntimeError):
    """Raised when browser_substrate.enabled but its dependencies are missing."""


def register_browser_substrate_tools(loop: Any, config: Any) -> bool:
    """Register substrate tools onto ``loop.tools`` based on ``config``.

    Returns ``True`` when tools were registered, ``False`` when disabled.
    """
    tools_cfg = getattr(config, "tools", None)
    bs_cfg = getattr(tools_cfg, "browser_substrate", None)
    if bs_cfg is None or not getattr(bs_cfg, "enabled", False):
        return False

    mcp_servers = getattr(tools_cfg, "mcp_servers", None) or {}
    server_name = getattr(bs_cfg, "mcp_server", "playwright_daily")
    if server_name not in mcp_servers:
        raise SubstrateConfigurationError(
            f"tools.browser_substrate.enabled=true but tools.mcpServers."
            f"{server_name!r} is not configured. Either disable browser_substrate "
            f"or add the MCP server config."
        )

    cache = TabEventCache(
        network_max=int(getattr(bs_cfg, "network_cache_max", 500)),
        console_max=int(getattr(bs_cfg, "console_cache_max", 200)),
        errors_max=int(getattr(bs_cfg, "errors_cache_max", 100)),
    )
    client = BrowserSubstrateClient(
        mcp_server_name=server_name,
        tool_registry=loop.tools,
        event_cache=cache,
    )
    fetch_tool = BrowserFetchTool(
        client=client,
        body_max_bytes=int(getattr(bs_cfg, "body_max_bytes", 65536)),
    )
    registry = SiteAdapterRegistry.for_directory(
        getattr(bs_cfg, "adapter_dir", "~/.ava/browser-sites")
    ).load()

    loop.tools.register(fetch_tool)
    loop.tools.register(BrowserEventsTool(client=client))
    loop.tools.register(SiteAdapterListTool(registry=registry))
    loop.tools.register(SiteAdapterInfoTool(registry=registry))
    loop.tools.register(
        SiteAdapterRunTool(registry=registry, client=client, fetch_tool=fetch_tool)
    )
    return True
