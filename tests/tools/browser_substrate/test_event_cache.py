"""Unit tests for TabEventCache (AVA-58, plan §F step 3)."""

from __future__ import annotations

import pytest

from ava.tools.browser_substrate.event_cache import TabEventCache


def _cache() -> TabEventCache:
    return TabEventCache(network_max=4, console_max=3, errors_max=2)


def test_seq_is_monotonic_per_event_type() -> None:
    cache = _cache()
    a = cache.append("tab-A", "network", {"url": "/a", "method": "GET"})
    b = cache.append("tab-A", "network", {"url": "/b", "method": "GET"})
    c = cache.append("tab-A", "console", {"text": "hi", "level": "info"})
    d = cache.append("tab-A", "network", {"url": "/c", "method": "GET"})

    # network seq 0,1,2 — independent of console
    assert (a, b, d) == (0, 1, 2)
    # console seq starts at 0 too
    assert c == 0


def test_per_tab_isolation() -> None:
    cache = _cache()
    cache.append("tab-A", "network", {"url": "/x"})
    seq_b = cache.append("tab-B", "network", {"url": "/y"})
    # tab-B's seq starts at 0 — caches are isolated
    assert seq_b == 0
    res_a = cache.query("tab-A", "network", since="0")
    assert [e["url"] for e in res_a["events"]] == ["/x"]
    res_b = cache.query("tab-B", "network", since="0")
    assert [e["url"] for e in res_b["events"]] == ["/y"]


def test_since_last_action_filters_pre_action_events() -> None:
    cache = _cache()
    cache.append("t", "network", {"url": "/before"})
    cache.mark_action_boundary("t")
    cache.append("t", "network", {"url": "/after-1"})
    cache.append("t", "network", {"url": "/after-2"})

    res = cache.query("t", "network", since="last_action")
    assert [e["url"] for e in res["events"]] == ["/after-1", "/after-2"]
    # next_cursor advances past last appended
    assert res["next_cursor"] == "3"


def test_since_explicit_cursor_returns_post_cursor_events() -> None:
    cache = _cache()
    for i in range(3):
        cache.append("t", "network", {"url": f"/{i}"})
    res = cache.query("t", "network", since="1")
    assert [e["url"] for e in res["events"]] == ["/1", "/2"]


def test_invalid_cursor_raises() -> None:
    cache = _cache()
    cache.append("t", "network", {"url": "/x"})
    with pytest.raises(ValueError):
        cache.query("t", "network", since="abc")
    with pytest.raises(ValueError):
        cache.query("t", "network", since="-1")


def test_ring_buffer_evicts_oldest() -> None:
    cache = _cache()  # network_max=4
    for i in range(6):
        cache.append("t", "network", {"url": f"/{i}"})
    # only the newest 4 survive — but seq numbers preserve identity
    res = cache.query("t", "network", since="0")
    assert [e["seq"] for e in res["events"]] == [2, 3, 4, 5]
    assert [e["url"] for e in res["events"]] == ["/2", "/3", "/4", "/5"]


def test_clear_tab_drops_state() -> None:
    cache = _cache()
    cache.append("t", "network", {"url": "/x"})
    cache.mark_action_boundary("t")
    cache.clear_tab("t")
    res = cache.query("t", "network", since="last_action")
    assert res == {"events": [], "next_cursor": "0", "truncated": False}
    # appending again restarts seq
    assert cache.append("t", "network", {"url": "/y"}) == 0


def test_filters_by_url_method_status() -> None:
    cache = _cache()
    cache.append("t", "network", {"url": "/api/foo", "method": "GET", "status": 200})
    cache.append("t", "network", {"url": "/api/bar", "method": "POST", "status": 500})
    cache.append("t", "network", {"url": "/static/a.js", "method": "GET", "status": 200})

    only_api = cache.query("t", "network", since="0", url_contains="/api/")
    assert [e["url"] for e in only_api["events"]] == ["/api/foo", "/api/bar"]

    only_post = cache.query("t", "network", since="0", method="post")
    assert [e["url"] for e in only_post["events"]] == ["/api/bar"]

    only_500 = cache.query("t", "network", since="0", status=500)
    assert [e["url"] for e in only_500["events"]] == ["/api/bar"]


def test_console_filters_by_level_and_text() -> None:
    cache = _cache()
    cache.append("t", "console", {"level": "error", "text": "TypeError: foo"})
    cache.append("t", "console", {"level": "info", "text": "hello"})

    res = cache.query("t", "console", since="0", level="ERROR")
    assert [e["text"] for e in res["events"]] == ["TypeError: foo"]

    res2 = cache.query("t", "console", since="0", text_contains="TypeError")
    assert [e["text"] for e in res2["events"]] == ["TypeError: foo"]


def test_limit_and_truncated_flag() -> None:
    cache = _cache()
    for i in range(3):
        cache.append("t", "network", {"url": f"/{i}"})
    res = cache.query("t", "network", since="0", limit=2)
    assert len(res["events"]) == 2
    assert res["truncated"] is True


def test_unknown_event_type_rejected() -> None:
    cache = _cache()
    with pytest.raises(ValueError):
        cache.append("t", "performance", {})  # type: ignore[arg-type]
    with pytest.raises(ValueError):
        cache.query("t", "performance", since="0")  # type: ignore[arg-type]


def test_query_unknown_tab_returns_empty() -> None:
    cache = _cache()
    res = cache.query("ghost", "network", since="last_action")
    assert res == {"events": [], "next_cursor": "0", "truncated": False}


def test_zero_or_negative_caps_rejected() -> None:
    with pytest.raises(ValueError):
        TabEventCache(network_max=0, console_max=1, errors_max=1)
    with pytest.raises(ValueError):
        TabEventCache(network_max=1, console_max=-1, errors_max=1)


def test_payload_is_copied_on_append() -> None:
    cache = _cache()
    payload = {"url": "/x", "tag": "live"}
    cache.append("t", "network", payload)
    payload["tag"] = "mutated"
    res = cache.query("t", "network", since="0")
    assert res["events"][0]["tag"] == "live"
