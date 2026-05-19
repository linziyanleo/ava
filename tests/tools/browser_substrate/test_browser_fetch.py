"""Security/contract tests for BrowserFetchTool (AVA-58, plan §F step 5)."""

from __future__ import annotations

import json
from typing import Any, Mapping

import pytest

from ava.tools.browser_substrate import (
    BrowserFetchTool,
    BrowserSubstrateClient,
    TabEventCache,
)
from ava.tools.browser_substrate import fetch_tool as fetch_tool_mod


class _FakeRegistry:
    """Mocks nanobot ToolRegistry: records calls + returns canned strings."""

    def __init__(self, response: str) -> None:
        self._response = response
        self.calls: list[tuple[str, dict[str, Any]]] = []

    def has(self, name: str) -> bool:
        return name == "mcp_playwright_daily_browser_evaluate"

    async def execute(self, name: str, params: Mapping[str, Any]) -> Any:
        self.calls.append((name, dict(params)))
        return self._response


def _success_payload(**override: Any) -> str:
    payload: dict[str, Any] = {
        "ok": True,
        "url": "https://example.test/api/foo",
        "status": 200,
        "headers": {"content-type": "application/json"},
        "content_type": "application/json",
        "truncated": False,
        "body": None,
        "json": None,
    }
    payload.update(override)
    return json.dumps(payload)


def _build(response: str = _success_payload(), body_max_bytes: int = 65536) -> tuple[BrowserFetchTool, _FakeRegistry, BrowserSubstrateClient]:
    cache = TabEventCache(network_max=8, console_max=4, errors_max=4)
    reg = _FakeRegistry(response)
    client = BrowserSubstrateClient(
        mcp_server_name="playwright_daily",
        tool_registry=reg,
        event_cache=cache,
    )
    return BrowserFetchTool(client=client, body_max_bytes=body_max_bytes), reg, client


# ----- security boundary: methods --------------------------------------


@pytest.mark.parametrize("method", ["POST", "PUT", "PATCH", "DELETE", "OPTIONS"])
@pytest.mark.asyncio
async def test_unsafe_method_blocked_before_mcp(method: str) -> None:
    tool, reg, _ = _build()
    out = json.loads(await tool.execute(url="/api/foo", method=method))
    assert out["ok"] is False
    assert "GET/HEAD" in out["error"]
    assert reg.calls == []  # NEVER reach MCP


@pytest.mark.asyncio
async def test_get_and_head_allowed() -> None:
    for m in ("GET", "HEAD", "get", "head"):
        tool, reg, _ = _build()
        out = json.loads(await tool.execute(url="/x", method=m))
        assert out["ok"] is True
        assert reg.calls, f"method {m!r} did not reach MCP"


# ----- security boundary: headers --------------------------------------


@pytest.mark.asyncio
async def test_caller_supplied_auth_headers_stripped() -> None:
    tool, reg, _ = _build()
    out = json.loads(
        await tool.execute(
            url="/x",
            headers={
                "Cookie": "sid=abc",
                "Authorization": "Bearer xyz",
                "Origin": "https://evil.test",
                "X-Trace": "keep-me",
            },
        )
    )
    assert out["ok"] is True
    assert set(out["stripped_headers"]) == {"Cookie", "Authorization", "Origin"}

    # Also confirm the JS template did NOT carry the stripped headers.
    fn = reg.calls[0][1]["function"]
    assert "sid=abc" not in fn
    assert "Bearer xyz" not in fn
    assert "X-Trace" in fn  # benign header preserved


# ----- security boundary: URL/origin -----------------------------------


@pytest.mark.asyncio
async def test_absolute_url_without_allowed_origins_rejected() -> None:
    tool, reg, _ = _build()
    out = json.loads(await tool.execute(url="https://evil.test/x"))
    assert out["ok"] is False
    assert "allowed_origins" in out["error"]
    assert reg.calls == []


@pytest.mark.asyncio
async def test_absolute_url_origin_must_match_allowlist() -> None:
    tool, reg, _ = _build()
    out = json.loads(
        await tool.execute(
            url="https://other.test/x",
            allowed_origins=["https://example.test"],
        )
    )
    assert out["ok"] is False
    assert "not in allowed_origins" in out["error"]
    assert reg.calls == []


@pytest.mark.asyncio
async def test_absolute_url_in_allowlist_accepted() -> None:
    tool, reg, _ = _build()
    out = json.loads(
        await tool.execute(
            url="https://example.test/x",
            allowed_origins=["https://example.test"],
        )
    )
    assert out["ok"] is True
    assert len(reg.calls) == 1


@pytest.mark.asyncio
async def test_relative_url_does_not_require_allowed_origins() -> None:
    tool, reg, _ = _build()
    out = json.loads(await tool.execute(url="/api/foo"))
    assert out["ok"] is True
    assert len(reg.calls) == 1


# ----- body capture ----------------------------------------------------


@pytest.mark.asyncio
async def test_body_capture_default_off() -> None:
    tool, reg, _ = _build(_success_payload(body=None, json=None))
    out = json.loads(await tool.execute(url="/x"))
    assert "body" not in out
    # verify the JS got with_body=false
    fn = reg.calls[0][1]["function"]
    assert "const __WITH_BODY__ = false" in fn


@pytest.mark.asyncio
async def test_body_capture_with_body_returns_payload() -> None:
    tool, reg, _ = _build(_success_payload(body="hello", json=None))
    out = json.loads(await tool.execute(url="/x", with_body=True))
    assert out["body"] == "hello"


@pytest.mark.asyncio
async def test_body_truncated_flag_propagated() -> None:
    tool, reg, _ = _build(_success_payload(body="abc", truncated=True))
    out = json.loads(await tool.execute(url="/x", with_body=True))
    assert out["truncated"] is True


@pytest.mark.asyncio
async def test_body_max_bytes_passed_to_template() -> None:
    tool, reg, _ = _build(body_max_bytes=4096)
    await tool.execute(url="/x", with_body=True)
    fn = reg.calls[0][1]["function"]
    assert "const __BODY_MAX__ = 4096" in fn


# ----- contract: cache + cursor ----------------------------------------


@pytest.mark.asyncio
async def test_records_event_in_network_cache() -> None:
    tool, reg, client = _build(_success_payload(status=204))
    out = json.loads(await tool.execute(url="/x", method="HEAD"))
    assert out["seq"] == 0
    assert out["cursor"] == "1"
    cached = client.cache().query("playwright_daily:active", "network", since="0")
    assert [e["seq"] for e in cached["events"]] == [0]
    assert cached["events"][0]["status"] == 204


@pytest.mark.asyncio
async def test_marks_action_boundary_so_subsequent_events_isolate() -> None:
    tool, _, client = _build(_success_payload())
    await tool.execute(url="/x")
    # external event recorded after action boundary should be visible via since=last_action
    client.append_event("playwright_daily:active", "network", {"url": "/y", "method": "GET"})
    res = client.cache().query("playwright_daily:active", "network", since="last_action")
    assert [e["url"] for e in res["events"]] == ["/y"]


# ----- error propagation -----------------------------------------------


@pytest.mark.asyncio
async def test_runner_error_string_returned_as_failure() -> None:
    tool, _, _ = _build("Error: target page closed")
    out = json.loads(await tool.execute(url="/x"))
    assert out["ok"] is False
    assert "target page closed" in out["error"]


@pytest.mark.asyncio
async def test_non_json_response_falls_through() -> None:
    tool, _, _ = _build("totally not json")
    out = json.loads(await tool.execute(url="/x"))
    assert out["ok"] is False
    assert "non-JSON" in out["error"] or "fetch failed" in out["error"]


@pytest.mark.asyncio
async def test_empty_url_rejected() -> None:
    tool, reg, _ = _build()
    out = json.loads(await tool.execute(url=""))
    assert out["ok"] is False
    assert reg.calls == []


# ----- security: tool surface ------------------------------------------


def test_tool_name_is_browser_fetch_no_eval_in_name() -> None:
    tool, _, _ = _build()
    assert tool.name == "browser_fetch"
    bad = ("eval", "evaluate", "execute_script", "javascript")
    assert not any(b in tool.name for b in bad)


def test_fetch_template_is_module_constant() -> None:
    """Q3: callers cannot influence the JS template."""
    assert isinstance(fetch_tool_mod._FETCH_TEMPLATE, str)
    assert fetch_tool_mod._FETCH_TEMPLATE.startswith("async () =>")
    # template references the placeholder names — no other interpolation slots
    placeholders = ("%(url)s", "%(method)s", "%(headers)s", "%(with_body)s", "%(body_max)s")
    for ph in placeholders:
        assert ph in fetch_tool_mod._FETCH_TEMPLATE
    # nothing else like %(... )s
    import re
    extras = re.findall(r"%\([^)]+\)s", fetch_tool_mod._FETCH_TEMPLATE)
    assert set(extras) == set(placeholders)


@pytest.mark.asyncio
async def test_template_constant_substitution_is_json_encoded() -> None:
    """A malicious-looking URL/header is JSON-encoded so a JS parser would
    parse it back to the *exact same Python value* (no JS injection)."""
    import re as _re
    tool, reg, _ = _build()
    weird = '"; alert(1); //'
    await tool.execute(
        url="/x",
        headers={"X-Crafted": weird},
    )
    fn = reg.calls[0][1]["function"]
    # Pull the JSON literal we wrote next to __HEADERS__
    m = _re.search(r"const __HEADERS__ = (\{.*?\});", fn)
    assert m, "headers slot not found in template"
    parsed_headers = json.loads(m.group(1))
    assert parsed_headers == {"X-Crafted": weird}
    # Same for URL slot
    m2 = _re.search(r"const __URL__ = (\".*?\");", fn)
    assert m2 and json.loads(m2.group(1)) == "/x"


@pytest.mark.asyncio
async def test_body_max_bytes_zero_rejected_at_init() -> None:
    cache = TabEventCache(network_max=8, console_max=4, errors_max=4)
    client = BrowserSubstrateClient(
        mcp_server_name="playwright_daily",
        tool_registry=_FakeRegistry(_success_payload()),
        event_cache=cache,
    )
    with pytest.raises(ValueError):
        BrowserFetchTool(client=client, body_max_bytes=0)
