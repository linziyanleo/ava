from __future__ import annotations

from ava.console.services.tunnel_service import TunnelService


class _FakeProcess:
    pid = 1234

    def __init__(self):
        self.stdout = ["INF +--------------------------------------------------------------------------------------------+\n"]
        self.stderr = ["INF https://example.trycloudflare.com\n"]
        self._terminated = False

    def poll(self):
        return None if not self._terminated else 0

    def terminate(self):
        self._terminated = True

    def wait(self, timeout=None):
        return 0


def test_tunnel_service_parses_public_url_and_stops(tmp_path, monkeypatch):
    binary = tmp_path / "vendor" / "cloudflared" / "darwin-arm64" / "cloudflared"
    binary.parent.mkdir(parents=True)
    binary.write_text("#!/bin/sh\n", encoding="utf-8")
    fake_process = _FakeProcess()
    monkeypatch.setattr("ava.console.services.tunnel_service.platform.system", lambda: "Darwin")
    monkeypatch.setattr("ava.console.services.tunnel_service.platform.machine", lambda: "arm64")
    monkeypatch.setattr("ava.console.services.tunnel_service.subprocess.Popen", lambda *args, **kwargs: fake_process)

    service = TunnelService(repo_root=tmp_path, console_port=6688)
    started = service.start()

    assert started.running is True
    assert started.public_url == "https://example.trycloudflare.com"
    assert service.stop().running is False
