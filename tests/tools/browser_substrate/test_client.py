"""Unit tests for BrowserSubstrateClient skeleton (AVA-58, plan §F step 4)."""

from __future__ import annotations

from typing import Any, Mapping

import pytest

from ava.tools.browser_substrate.client import (
    BrowserSubstrateClient,
    MCPToolMissing,
    SubstrateError,
)
from ava.tools.browser_substrate.event_cache import TabEventCache


class _FakeRegistry:
    def __init__(self, *, registered: dict[str, str] | None = None) -> None:
        self.registered = registered or {}
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def has(self, name: str) -> bool:
        return name in self.registered

    async def execute(self, name: str, params: Mapping[str, Any]) -> Any:
        self.calls.append((name, dict(params)))
        return self.registered[name]


def _client(registry: Any | None = None, **caps: int) -> BrowserSubstrateClient:
    cache = TabEventCache(
        network_max=caps.get("network_max", 8),
        console_max=caps.get("console_max", 4),
        errors_max=caps.get("errors_max", 4),
    )
    return BrowserSubstrateClient(
        mcp_server_name="playwright_daily",
        tool_registry=registry,
        event_cache=cache,
    )


def test_mcp_tool_name_uses_sanitized_server() -> None:
    cache = TabEventCache(network_max=8, console_max=4, errors_max=4)
    c = BrowserSubstrateClient(
        mcp_server_name="playwright daily!",
        tool_registry=None,
        event_cache=cache,
    )
    assert c.mcp_server_name == "playwright_daily_"
    assert c.mcp_tool_name("browser_evaluate") == "mcp_playwright_daily__browser_evaluate"


@pytest.mark.asyncio
async def test_call_mcp_forwards_args_and_returns_string() -> None:
    reg = _FakeRegistry(
        registered={"mcp_playwright_daily_browser_evaluate": "ok"},
    )
    c = _client(reg)
    out = await c.call_mcp("browser_evaluate", {"function": "()=>1"})
    assert out == "ok"
    assert reg.calls == [("mcp_playwright_daily_browser_evaluate", {"function": "()=>1"})]


@pytest.mark.asyncio
async def test_call_mcp_raises_when_tool_missing() -> None:
    reg = _FakeRegistry(registered={})
    c = _client(reg)
    with pytest.raises(MCPToolMissing) as exc:
        await c.call_mcp("browser_evaluate", {})
    assert "playwright_daily" in str(exc.value)


@pytest.mark.asyncio
async def test_call_mcp_raises_without_registry() -> None:
    c = _client(None)
    with pytest.raises(SubstrateError):
        await c.call_mcp("browser_evaluate", {})


@pytest.mark.asyncio
async def test_call_mcp_serialises_non_string_result() -> None:
    reg = _FakeRegistry(
        registered={"mcp_playwright_daily_browser_evaluate": 42},
    )
    c = _client(reg)
    out = await c.call_mcp("browser_evaluate", {})
    assert out == "42"


@pytest.mark.asyncio
async def test_with_active_tab_provides_active_key() -> None:
    c = _client()
    seen: list[str] = []

    async def _action(tab_key: str) -> str:
        seen.append(tab_key)
        return tab_key

    out = await c.with_active_tab(_action)
    assert out == "playwright_daily:active"
    assert seen == ["playwright_daily:active"]


def test_cache_passthroughs() -> None:
    c = _client()
    seq = c.append_event("playwright_daily:active", "network", {"url": "/x"})
    assert seq == 0
    c.mark_action_boundary("playwright_daily:active")
    seq2 = c.append_event("playwright_daily:active", "network", {"url": "/y"})
    assert seq2 == 1
    res = c.cache().query("playwright_daily:active", "network", since="last_action")
    assert [e["url"] for e in res["events"]] == ["/y"]
    c.clear_tab("playwright_daily:active")
    assert c.cache().query("playwright_daily:active", "network", since="0") == {
        "events": [],
        "next_cursor": "0",
        "truncated": False,
    }
