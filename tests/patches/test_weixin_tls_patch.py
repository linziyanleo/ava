"""Tests for weixin_tls_patch."""

from __future__ import annotations

import asyncio
from pathlib import Path


def test_apply_weixin_tls_patch_is_idempotent():
    from ava.patches.weixin_tls_patch import apply_weixin_tls_patch

    first = apply_weixin_tls_patch()
    second = apply_weixin_tls_patch()

    assert "trust" in first.lower() or "weixin" in first.lower()
    assert "skipped" in second.lower()


def test_weixin_login_uses_system_ssl_context(monkeypatch, tmp_path: Path):
    import nanobot.channels.weixin as weixin_mod
    from ava.patches.weixin_tls_patch import apply_weixin_tls_patch

    apply_weixin_tls_patch()

    sentinel_ctx = object()
    captured: list[dict] = []

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            captured.append(kwargs)

        async def aclose(self):
            return None

    monkeypatch.setattr("ava.patches.weixin_tls_patch.ssl.create_default_context", lambda: sentinel_ctx)
    monkeypatch.setattr(weixin_mod.httpx, "AsyncClient", FakeAsyncClient)

    channel = weixin_mod.WeixinChannel({"enabled": True, "allowFrom": []}, bus=None)
    channel._state_dir = tmp_path / "weixin"

    async def fake_qr_login():
        return True

    monkeypatch.setattr(channel, "_qr_login", fake_qr_login)

    assert asyncio.run(channel.login(force=True)) is True
    assert captured
    assert captured[0]["verify"] is sentinel_ctx


def test_weixin_start_uses_system_ssl_context(monkeypatch):
    import nanobot.channels.weixin as weixin_mod
    from ava.patches.weixin_tls_patch import apply_weixin_tls_patch

    apply_weixin_tls_patch()

    sentinel_ctx = object()
    captured: list[dict] = []

    class FakeAsyncClient:
        def __init__(self, *args, **kwargs):
            captured.append(kwargs)

        async def aclose(self):
            return None

    monkeypatch.setattr("ava.patches.weixin_tls_patch.ssl.create_default_context", lambda: sentinel_ctx)
    monkeypatch.setattr(weixin_mod.httpx, "AsyncClient", FakeAsyncClient)

    channel = weixin_mod.WeixinChannel(
        {"enabled": True, "allowFrom": [], "token": "token-value"},
        bus=None,
    )

    async def fake_poll_once():
        channel._running = False

    monkeypatch.setattr(channel, "_poll_once", fake_poll_once)

    asyncio.run(channel.start())

    assert captured
    assert captured[0]["verify"] is sentinel_ctx
