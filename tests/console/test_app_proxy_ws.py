from __future__ import annotations

import pytest

from ava.console.app import _close_upstream_if_needed, _close_websocket_if_needed, _proxy_close_params


class _Closable:
    def __init__(self):
        self.calls: list[tuple[int, str]] = []

    async def close(self, *, code: int = 1000, reason: str = ""):
        self.calls.append((code, reason))


def test_proxy_close_params_preserve_explicit_code_and_reason():
    assert _proxy_close_params(4001, "driver-close") == (4001, "driver-close")


def test_proxy_close_params_fall_back_when_missing():
    assert _proxy_close_params(None, None, fallback_code=1011, fallback_reason="Gateway unreachable") == (
        1011,
        "Gateway unreachable",
    )


@pytest.mark.asyncio
async def test_close_upstream_passes_code_and_reason():
    upstream = _Closable()

    await _close_upstream_if_needed(upstream, code=4001, reason="driver-close")

    assert upstream.calls == [(4001, "driver-close")]


@pytest.mark.asyncio
async def test_close_websocket_passes_code_and_reason():
    websocket = _Closable()

    await _close_websocket_if_needed(websocket, code=1000, reason="")

    assert websocket.calls == [(1000, "")]
