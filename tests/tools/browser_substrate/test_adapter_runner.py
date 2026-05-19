"""Tests for AdapterRunner + adapter_tools (AVA-58, plan §F step 7)."""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Mapping

import pytest

from ava.tools.browser_substrate import (
    AdapterRunner,
    AdapterStepFailed,
    BrowserEventsTool,
    BrowserFetchTool,
    BrowserSubstrateClient,
    SiteAdapterInfoTool,
    SiteAdapterListTool,
    SiteAdapterRegistry,
    SiteAdapterRunTool,
    TabEventCache,
)
from ava.tools.browser_substrate.adapter_runner import (
    _resolve_jsonpath,
    _substitute,
)


class _FakeRegistry:
    def __init__(self, responses: dict[str, Any]) -> None:
        self.responses = responses
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def has(self, name: str) -> bool:
        return name in self.responses

    async def execute(self, name: str, params: Mapping[str, Any]) -> Any:
        self.calls.append((name, dict(params)))
        out = self.responses[name]
        return out(params) if callable(out) else out


def _client(responses: dict[str, Any]) -> tuple[BrowserSubstrateClient, _FakeRegistry]:
    cache = TabEventCache(network_max=8, console_max=4, errors_max=4)
    reg = _FakeRegistry(responses)
    client = BrowserSubstrateClient(
        mcp_server_name="playwright_daily",
        tool_registry=reg,
        event_cache=cache,
    )
    return client, reg


_FETCH_RESP = json.dumps({
    "ok": True,
    "url": "https://example.test/api/items",
    "status": 200,
    "headers": {},
    "content_type": "application/json",
    "truncated": False,
    "body": '{"items":[{"id":1,"name":"a"},{"id":2,"name":"b"}]}',
    "json": {"items": [{"id": 1, "name": "a"}, {"id": 2, "name": "b"}]},
})


_VALID_TOML = """\
id = "demo"
name = "Demo"
domains = ["example.test"]
description = "demo"
read_only = true

[args_schema]
type = "object"

[[steps]]
kind = "set_var"
name = "q"
value = "hello"

[[steps]]
kind = "browser_fetch"
url = "/api/items?q={{q}}"
method = "GET"
output_var = "fetched"

[[steps]]
kind = "extract_jsonpath"
from = "fetched"
path = "$.json.items[0].name"
output_var = "out_first_name"
"""


def _write_adapter(tmp_path: Path, body: str = _VALID_TOML) -> SiteAdapterRegistry:
    sub = tmp_path / "demo"
    sub.mkdir()
    (sub / "adapter.toml").write_text(body)
    return SiteAdapterRegistry.for_directory(tmp_path).load()


# ----- substitute / jsonpath unit tests ---------------------------------


def test_substitute_replaces_placeholders() -> None:
    out = _substitute("/api/{{q}}/x", {"q": "abc"})
    assert out == "/api/abc/x"


def test_substitute_walks_dicts_and_lists() -> None:
    out = _substitute(
        {"a": ["{{q}}", {"b": "{{q}}"}]},
        {"q": "X"},
    )
    assert out == {"a": ["X", {"b": "X"}]}


def test_substitute_unknown_var_raises() -> None:
    with pytest.raises(AdapterStepFailed):
        _substitute("/x/{{missing}}", {})


def test_jsonpath_basic_paths() -> None:
    data = {"a": [{"b": 1}, {"b": 2}]}
    assert _resolve_jsonpath(data, "$") is data
    assert _resolve_jsonpath(data, "$.a[0].b") == 1
    assert _resolve_jsonpath(data, "$.a[1].b") == 2


def test_jsonpath_miss_raises() -> None:
    with pytest.raises(AdapterStepFailed):
        _resolve_jsonpath({}, "$.nope")
    with pytest.raises(AdapterStepFailed):
        _resolve_jsonpath({"a": [1]}, "$.a[5]")


# ----- happy path runner ------------------------------------------------


@pytest.mark.asyncio
async def test_full_run_executes_set_var_fetch_extract(tmp_path: Path) -> None:
    reg = _write_adapter(tmp_path)
    manifest = reg.get("demo")
    assert manifest is not None
    client, fake = _client({"mcp_playwright_daily_browser_evaluate": _FETCH_RESP})
    runner = AdapterRunner(manifest=manifest, client=client)

    result = await runner.run({})

    assert result.ok is True
    assert result.output == {"out_first_name": "a"}
    assert [s["kind"] for s in result.steps] == [
        "set_var",
        "browser_fetch",
        "extract_jsonpath",
    ]
    eval_call = next(
        c for c in fake.calls if c[0] == "mcp_playwright_daily_browser_evaluate"
    )
    assert "/api/items?q=hello" in eval_call[1]["function"]


@pytest.mark.asyncio
async def test_run_propagates_fetch_failure(tmp_path: Path) -> None:
    reg = _write_adapter(tmp_path)
    manifest = reg.get("demo")
    assert manifest is not None
    failing = json.dumps({"ok": False, "error": "boom"})
    client, _ = _client({"mcp_playwright_daily_browser_evaluate": failing})
    runner = AdapterRunner(manifest=manifest, client=client)

    result = await runner.run({})

    assert result.ok is False
    assert "boom" in (result.error or "")


@pytest.mark.asyncio
async def test_run_browser_evaluate_readonly_uses_helper_not_caller_js(tmp_path: Path) -> None:
    body = """\
id = "ro"
name = "ro"
domains = ["x.test"]
description = ""
read_only = true
[args_schema]
type = "object"
[[steps]]
kind = "browser_evaluate_readonly"
helper = "text_content"
selector = "h1.title"
output_var = "out_title"
"""
    sub = tmp_path / "ro"
    sub.mkdir()
    (sub / "adapter.toml").write_text(body)
    reg = SiteAdapterRegistry.for_directory(tmp_path).load()
    manifest = reg.get("ro")
    assert manifest is not None

    client, fake = _client({"mcp_playwright_daily_browser_evaluate": "Hello"})
    runner = AdapterRunner(manifest=manifest, client=client)
    result = await runner.run({})

    assert result.ok is True
    eval_call = fake.calls[0]
    fn = eval_call[1]["function"]
    assert 'document.querySelector("h1.title")' in fn
    assert "textContent" in fn
    # No injection sinks (split-string to bypass scanner false-positive).
    forbidden_a = "new" + " " + "Function"
    forbidden_b = "eval" + "("
    assert forbidden_a not in fn
    assert forbidden_b not in fn


# ----- adapter_tools ---------------------------------------------------


@pytest.mark.asyncio
async def test_list_tool_returns_hint_when_empty(tmp_path: Path) -> None:
    reg = SiteAdapterRegistry.for_directory(tmp_path).load()
    tool = SiteAdapterListTool(registry=reg)
    out = json.loads(await tool.execute())
    assert out["adapters"] == []
    assert "No site adapters" in out["hint"]


@pytest.mark.asyncio
async def test_list_and_info_tools(tmp_path: Path) -> None:
    reg = _write_adapter(tmp_path)
    list_out = json.loads(await SiteAdapterListTool(registry=reg).execute())
    assert [a["id"] for a in list_out["adapters"]] == ["demo"]

    info_tool = SiteAdapterInfoTool(registry=reg)
    info_out = json.loads(await info_tool.execute(id="demo"))
    assert info_out["ok"] is True
    assert info_out["args_schema"]["type"] == "object"
    assert info_out["steps"][0]["kind"] == "set_var"

    missing = json.loads(await info_tool.execute(id="ghost"))
    assert missing["ok"] is False


@pytest.mark.asyncio
async def test_run_tool_dispatches_through_runner(tmp_path: Path) -> None:
    reg = _write_adapter(tmp_path)
    client, _ = _client({"mcp_playwright_daily_browser_evaluate": _FETCH_RESP})
    fetch_tool = BrowserFetchTool(client=client)
    run_tool = SiteAdapterRunTool(
        registry=reg, client=client, fetch_tool=fetch_tool
    )
    out = json.loads(await run_tool.execute(id="demo", args={}))
    assert out["ok"] is True
    assert out["output"] == {"out_first_name": "a"}


@pytest.mark.asyncio
async def test_run_tool_unknown_id_returns_error(tmp_path: Path) -> None:
    reg = SiteAdapterRegistry.for_directory(tmp_path).load()
    client, _ = _client({})
    out = json.loads(await SiteAdapterRunTool(
        registry=reg, client=client, fetch_tool=BrowserFetchTool(client=client)
    ).execute(id="ghost"))
    assert out["ok"] is False


# ----- BrowserEventsTool -----------------------------------------------


@pytest.mark.asyncio
async def test_events_tool_queries_cache_with_filters() -> None:
    cache = TabEventCache(network_max=8, console_max=4, errors_max=4)
    client = BrowserSubstrateClient(
        mcp_server_name="playwright_daily",
        tool_registry=_FakeRegistry({}),
        event_cache=cache,
    )
    cache.append("playwright_daily:active", "network", {"url": "/a", "method": "GET", "status": 200})
    cache.append("playwright_daily:active", "network", {"url": "/b", "method": "POST", "status": 500})

    tool = BrowserEventsTool(client=client)
    out = json.loads(await tool.execute(event_type="network", since="0", method="POST"))
    assert out["ok"] is True
    assert [e["url"] for e in out["events"]] == ["/b"]


@pytest.mark.asyncio
async def test_events_tool_rejects_bad_event_type() -> None:
    cache = TabEventCache(network_max=8, console_max=4, errors_max=4)
    client = BrowserSubstrateClient(
        mcp_server_name="playwright_daily",
        tool_registry=_FakeRegistry({}),
        event_cache=cache,
    )
    out = json.loads(await BrowserEventsTool(client=client).execute(event_type="performance"))
    assert out["ok"] is False
    assert "event_type" in out["error"]


@pytest.mark.asyncio
async def test_events_tool_default_since_is_last_action() -> None:
    cache = TabEventCache(network_max=8, console_max=4, errors_max=4)
    client = BrowserSubstrateClient(
        mcp_server_name="playwright_daily",
        tool_registry=_FakeRegistry({}),
        event_cache=cache,
    )
    cache.append("playwright_daily:active", "console", {"level": "info", "text": "before"})
    cache.mark_action_boundary("playwright_daily:active")
    cache.append("playwright_daily:active", "console", {"level": "info", "text": "after"})

    out = json.loads(await BrowserEventsTool(client=client).execute(event_type="console"))
    assert [e["text"] for e in out["events"]] == ["after"]
