"""Registration wiring tests (AVA-58, plan §F step 8)."""

from __future__ import annotations

from types import SimpleNamespace
from typing import Any

import pytest

from ava.tools.browser_substrate import (
    BrowserEventsTool,
    BrowserFetchTool,
    SiteAdapterInfoTool,
    SiteAdapterListTool,
    SiteAdapterRunTool,
    SubstrateConfigurationError,
    register_browser_substrate_tools,
)


class _ToolsRegistry:
    def __init__(self) -> None:
        self.registered: list[Any] = []

    def register(self, tool: Any) -> None:
        self.registered.append(tool)

    def has(self, name: str) -> bool:
        return name in self._all_names()

    def _all_names(self) -> list[str]:
        return [getattr(t, "name", "") for t in self.registered]


class _Loop:
    def __init__(self) -> None:
        self.tools = _ToolsRegistry()


def _make_config(
    *,
    enabled: bool,
    mcp_servers: dict[str, Any] | None = None,
    mcp_server: str = "playwright_daily",
    adapter_dir: str = "/tmp/ava-test-empty",
) -> SimpleNamespace:
    bs = SimpleNamespace(
        enabled=enabled,
        mcp_server=mcp_server,
        network_cache_max=8,
        console_cache_max=4,
        errors_cache_max=4,
        body_max_bytes=1024,
        adapter_dir=adapter_dir,
    )
    tools_ns = SimpleNamespace(
        browser_substrate=bs,
        mcp_servers=mcp_servers if mcp_servers is not None else {},
    )
    return SimpleNamespace(tools=tools_ns)


# ----- gating -----------------------------------------------------------


def test_disabled_does_not_register(tmp_path) -> None:
    loop = _Loop()
    cfg = _make_config(enabled=False, adapter_dir=str(tmp_path))
    out = register_browser_substrate_tools(loop, cfg)
    assert out is False
    assert loop.tools.registered == []


def test_enabled_without_mcp_server_raises(tmp_path) -> None:
    loop = _Loop()
    cfg = _make_config(enabled=True, mcp_servers={}, adapter_dir=str(tmp_path))
    with pytest.raises(SubstrateConfigurationError) as exc:
        register_browser_substrate_tools(loop, cfg)
    assert "playwright_daily" in str(exc.value)
    assert loop.tools.registered == []


def test_enabled_with_mcp_server_registers_five_tools(tmp_path) -> None:
    loop = _Loop()
    cfg = _make_config(
        enabled=True,
        mcp_servers={"playwright_daily": object()},
        adapter_dir=str(tmp_path),
    )
    out = register_browser_substrate_tools(loop, cfg)
    assert out is True
    names = [t.name for t in loop.tools.registered]
    assert names == [
        "browser_fetch",
        "browser_events",
        "site_adapter_list",
        "site_adapter_info",
        "site_adapter_run",
    ]


def test_registered_tool_types_match_expected(tmp_path) -> None:
    loop = _Loop()
    cfg = _make_config(
        enabled=True,
        mcp_servers={"playwright_daily": object()},
        adapter_dir=str(tmp_path),
    )
    register_browser_substrate_tools(loop, cfg)
    types = [type(t) for t in loop.tools.registered]
    assert types == [
        BrowserFetchTool,
        BrowserEventsTool,
        SiteAdapterListTool,
        SiteAdapterInfoTool,
        SiteAdapterRunTool,
    ]


def test_custom_mcp_server_name_is_honored(tmp_path) -> None:
    loop = _Loop()
    cfg = _make_config(
        enabled=True,
        mcp_servers={"alt_server": object()},
        mcp_server="alt_server",
        adapter_dir=str(tmp_path),
    )
    register_browser_substrate_tools(loop, cfg)
    fetch = loop.tools.registered[0]
    assert fetch._client.mcp_server_name == "alt_server"


def test_no_eval_named_tool_exposed(tmp_path) -> None:
    """Q3 surface guard — substrate must never register a tool whose name
    advertises raw script execution."""
    loop = _Loop()
    cfg = _make_config(
        enabled=True,
        mcp_servers={"playwright_daily": object()},
        adapter_dir=str(tmp_path),
    )
    register_browser_substrate_tools(loop, cfg)
    bad_substrings = ("eval", "execute_script", "javascript", "exec_js")
    for tool in loop.tools.registered:
        for bad in bad_substrings:
            assert bad not in tool.name, f"tool {tool.name!r} leaks {bad!r}"


def test_substrate_does_not_replace_mcp_playwright_daily_wrappers(tmp_path) -> None:
    """The substrate appends its own tools; it must not touch any tool name
    in the `mcp_playwright_daily_*` namespace."""
    loop = _Loop()
    # Pretend the loop has already registered upstream MCP wrappers.
    pre = [
        SimpleNamespace(name="mcp_playwright_daily_browser_evaluate"),
        SimpleNamespace(name="mcp_playwright_daily_browser_tabs"),
        SimpleNamespace(name="page_agent"),
    ]
    for t in pre:
        loop.tools.register(t)
    cfg = _make_config(
        enabled=True,
        mcp_servers={"playwright_daily": object()},
        adapter_dir=str(tmp_path),
    )
    register_browser_substrate_tools(loop, cfg)
    # The original tools must still be there at the same identity.
    assert loop.tools.registered[:3] == pre


def test_page_agent_tool_unchanged_when_substrate_enabled(tmp_path) -> None:
    """Substrate registration adds tools; `page_agent` registration is not
    in this code path, so it must not be modified or shadowed by name."""
    loop = _Loop()
    cfg = _make_config(
        enabled=True,
        mcp_servers={"playwright_daily": object()},
        adapter_dir=str(tmp_path),
    )
    register_browser_substrate_tools(loop, cfg)
    assert "page_agent" not in [t.name for t in loop.tools.registered]
    # And no substrate tool overlaps with the page_agent name.
    assert all(t.name != "page_agent" for t in loop.tools.registered)


def test_non_existent_adapter_dir_results_in_empty_registry(tmp_path) -> None:
    """Q5: empty/missing adapter dir yields an empty registry, no failure."""
    loop = _Loop()
    cfg = _make_config(
        enabled=True,
        mcp_servers={"playwright_daily": object()},
        adapter_dir=str(tmp_path / "does-not-exist"),
    )
    register_browser_substrate_tools(loop, cfg)
    list_tool = next(t for t in loop.tools.registered if t.name == "site_adapter_list")
    assert list_tool._registry.is_empty()
