"""Use the system trust store for Weixin channel HTTPS requests."""

from __future__ import annotations

import ssl

from ava.launcher import register_patch


def _build_weixin_client(*, httpx_mod, timeout):
    return httpx_mod.AsyncClient(
        timeout=timeout,
        follow_redirects=True,
        verify=ssl.create_default_context(),
    )


def apply_weixin_tls_patch() -> str:
    try:
        import nanobot.channels.weixin as weixin_mod
    except Exception as exc:
        return f"weixin TLS patch skipped ({exc})"

    WeixinChannel = weixin_mod.WeixinChannel
    if getattr(WeixinChannel, "_ava_weixin_tls_patch", False):
        return "weixin TLS patch already applied (skipped)"

    async def login(self, force: bool = False) -> bool:
        """Perform QR code login and save token. Returns True on success."""
        if force:
            self._token = ""
            self._get_updates_buf = ""
            state_file = self._get_state_dir() / "account.json"
            if state_file.exists():
                state_file.unlink()
        if self._token or self._load_state():
            return True

        self._client = _build_weixin_client(
            httpx_mod=weixin_mod.httpx,
            timeout=weixin_mod.httpx.Timeout(60, connect=30),
        )
        self._running = True
        try:
            return await self._qr_login()
        finally:
            self._running = False
            if self._client:
                await self._client.aclose()
                self._client = None

    async def start(self) -> None:
        self._running = True
        self._next_poll_timeout_s = self.config.poll_timeout
        self._client = _build_weixin_client(
            httpx_mod=weixin_mod.httpx,
            timeout=weixin_mod.httpx.Timeout(self._next_poll_timeout_s + 10, connect=30),
        )

        if self.config.token:
            self._token = self.config.token
        elif not self._load_state():
            if not await self._qr_login():
                weixin_mod.logger.error(
                    "WeChat login failed. Run 'nanobot channels login weixin' to authenticate."
                )
                self._running = False
                return

        weixin_mod.logger.info("WeChat channel starting with long-poll...")

        consecutive_failures = 0
        while self._running:
            try:
                await self._poll_once()
                consecutive_failures = 0
            except weixin_mod.httpx.TimeoutException:
                continue
            except Exception:
                if not self._running:
                    break
                consecutive_failures += 1
                if consecutive_failures >= weixin_mod.MAX_CONSECUTIVE_FAILURES:
                    consecutive_failures = 0
                    await weixin_mod.asyncio.sleep(weixin_mod.BACKOFF_DELAY_S)
                else:
                    await weixin_mod.asyncio.sleep(weixin_mod.RETRY_DELAY_S)

    WeixinChannel.login = login
    WeixinChannel.start = start
    WeixinChannel._ava_weixin_tls_patch = True
    return "Weixin channel uses system trust store for HTTPS requests"


register_patch("weixin_tls", apply_weixin_tls_patch)
