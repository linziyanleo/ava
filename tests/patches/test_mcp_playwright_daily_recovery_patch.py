from __future__ import annotations

import sys
from contextlib import asynccontextmanager
from types import ModuleType, SimpleNamespace
from typing import Any

import pytest


class _FakeTextContent:
    def __init__(self, text: str) -> None:
        self.text = text


def _make_tool_def(name: str) -> SimpleNamespace:
    return SimpleNamespace(
        name=name,
        description=f"{name} tool",
        inputSchema={"type": "object", "properties": {}},
    )


def _make_result(text: str, *, is_error: bool = False) -> SimpleNamespace:
    return SimpleNamespace(isError=is_error, content=[_FakeTextContent(text)])


@pytest.fixture
def fake_mcp_runtime(monkeypatch: pytest.MonkeyPatch) -> dict[str, Any]:
    runtime: dict[str, Any] = {"session": None, "params": []}

    mcp_mod = ModuleType("mcp")
    mcp_mod.types = SimpleNamespace(TextContent=_FakeTextContent)

    class _FakeStdioServerParameters:
        def __init__(self, command: str, args: list[str], env: dict | None = None) -> None:
            self.command = command
            self.args = args
            self.env = env

    class _FakeClientSession:
        def __init__(self, _read: object, _write: object) -> None:
            self._session = runtime["session"]

        async def __aenter__(self) -> object:
            return self._session

        async def __aexit__(self, exc_type, exc, tb) -> bool:
            return False

    @asynccontextmanager
    async def _fake_stdio_client(params: object):
        runtime["params"].append(params)
        yield object(), object()

    mcp_mod.ClientSession = _FakeClientSession
    mcp_mod.StdioServerParameters = _FakeStdioServerParameters
    monkeypatch.setitem(sys.modules, "mcp", mcp_mod)

    client_mod = ModuleType("mcp.client")
    stdio_mod = ModuleType("mcp.client.stdio")
    stdio_mod.stdio_client = _fake_stdio_client
    monkeypatch.setitem(sys.modules, "mcp.client", client_mod)
    monkeypatch.setitem(sys.modules, "mcp.client.stdio", stdio_mod)

    return runtime


@pytest.fixture
def patch_state(monkeypatch: pytest.MonkeyPatch):
    import nanobot.agent.tools.mcp as mcp_mod

    from ava.patches import mcp_playwright_daily_recovery_patch as patch_mod

    original_init = mcp_mod.MCPToolWrapper.__init__
    original_execute = mcp_mod.MCPToolWrapper.execute
    patch_mod._STATES.clear()

    yield patch_mod

    monkeypatch.setattr(mcp_mod.MCPToolWrapper, "__init__", original_init, raising=False)
    monkeypatch.setattr(mcp_mod.MCPToolWrapper, "execute", original_execute, raising=False)
    patch_mod._STATES.clear()


def _fake_config(command: str = "fake-playwright-mcp") -> SimpleNamespace:
    return SimpleNamespace(
        tools=SimpleNamespace(
            mcp_servers={
                "playwright_daily": SimpleNamespace(
                    type=None,
                    command=command,
                    args=["--extension", "--browser", "chrome"],
                    env={"PLAYWRIGHT_MCP_EXTENSION_TOKEN": "token"},
                )
            }
        )
    )


@pytest.mark.asyncio
async def test_closed_target_retries_tabs_in_fresh_session(
    fake_mcp_runtime: dict[str, Any],
    patch_state,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nanobot.agent.tools.mcp as mcp_mod

    monkeypatch.setattr("nanobot.config.loader.load_config", lambda: _fake_config())

    async def stale_call_tool(_name: str, arguments: dict) -> object:
        return _make_result(
            "### Error\nError: browserBackend.callTool: Target page, context or browser has been closed",
            is_error=True,
        )

    fresh_calls: list[tuple[str, dict]] = []

    async def fresh_call_tool(name: str, arguments: dict) -> object:
        fresh_calls.append((name, arguments))
        return _make_result("fresh ok")

    async def initialize() -> None:
        return None

    fake_mcp_runtime["session"] = SimpleNamespace(
        initialize=initialize,
        call_tool=fresh_call_tool,
    )

    patch_state.apply_playwright_daily_recovery_patch()
    wrapper = mcp_mod.MCPToolWrapper(
        SimpleNamespace(call_tool=stale_call_tool),
        "playwright_daily",
        _make_tool_def("browser_tabs"),
    )

    result = await wrapper.execute(action="new", url="https://example.com")

    assert result == "fresh ok"
    assert fresh_calls == [("browser_tabs", {"action": "new", "url": "https://example.com"})]
    assert fake_mcp_runtime["params"][0].command == "fake-playwright-mcp"
    assert fake_mcp_runtime["params"][0].args == ["--extension", "--browser", "chrome"]


@pytest.mark.asyncio
async def test_closed_snapshot_replays_last_successful_navigate(
    fake_mcp_runtime: dict[str, Any],
    patch_state,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nanobot.agent.tools.mcp as mcp_mod

    monkeypatch.setattr("nanobot.config.loader.load_config", lambda: _fake_config())

    async def nav_call_tool(_name: str, arguments: dict) -> object:
        return _make_result("navigated")

    async def stale_snapshot_call_tool(_name: str, arguments: dict) -> object:
        return _make_result(
            "### Error\nError: browserBackend.callTool: Target page, context or browser has been closed",
            is_error=True,
        )

    fresh_calls: list[tuple[str, dict]] = []

    async def fresh_call_tool(name: str, arguments: dict) -> object:
        fresh_calls.append((name, arguments))
        return _make_result(f"{name} ok")

    async def initialize() -> None:
        return None

    fake_mcp_runtime["session"] = SimpleNamespace(
        initialize=initialize,
        call_tool=fresh_call_tool,
    )

    patch_state.apply_playwright_daily_recovery_patch()
    navigate = mcp_mod.MCPToolWrapper(
        SimpleNamespace(call_tool=nav_call_tool),
        "playwright_daily",
        _make_tool_def("browser_navigate"),
    )
    snapshot = mcp_mod.MCPToolWrapper(
        SimpleNamespace(call_tool=stale_snapshot_call_tool),
        "playwright_daily",
        _make_tool_def("browser_snapshot"),
    )

    assert await navigate.execute(url="https://example.com") == "navigated"
    result = await snapshot.execute()

    assert result == "browser_snapshot ok"
    assert fresh_calls == [
        ("browser_navigate", {"url": "https://example.com"}),
        ("browser_snapshot", {}),
    ]


@pytest.mark.asyncio
async def test_non_playwright_server_keeps_original_error(
    fake_mcp_runtime: dict[str, Any],
    patch_state,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import nanobot.agent.tools.mcp as mcp_mod

    monkeypatch.setattr("nanobot.config.loader.load_config", lambda: _fake_config())

    async def stale_call_tool(_name: str, arguments: dict) -> object:
        return _make_result(
            "### Error\nError: browserBackend.callTool: Target page, context or browser has been closed",
            is_error=True,
        )

    fresh_calls: list[tuple[str, dict]] = []

    async def fresh_call_tool(name: str, arguments: dict) -> object:
        fresh_calls.append((name, arguments))
        return _make_result("fresh ok")

    async def initialize() -> None:
        return None

    fake_mcp_runtime["session"] = SimpleNamespace(
        initialize=initialize,
        call_tool=fresh_call_tool,
    )

    patch_state.apply_playwright_daily_recovery_patch()
    wrapper = mcp_mod.MCPToolWrapper(
        SimpleNamespace(call_tool=stale_call_tool),
        "other_server",
        _make_tool_def("browser_tabs"),
    )

    result = await wrapper.execute(action="new")

    assert result == "Error: browserBackend.callTool: Target page, context or browser has been closed"
    assert fresh_calls == []
