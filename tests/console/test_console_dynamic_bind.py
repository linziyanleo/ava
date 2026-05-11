from __future__ import annotations

import os
from types import SimpleNamespace

from ava.console.services.console_network_service import ConsoleNetworkService


def test_console_network_reload_uses_same_process_pid(tmp_path):
    lan_access = SimpleNamespace(read_state=lambda: {"enabled": True})
    lan_https = SimpleNamespace(ssl_paths=lambda: (None, None))
    tunnel = SimpleNamespace(public_url="")
    service = ConsoleNetworkService(
        nanobot_dir=tmp_path,
        port=6688,
        lan_access=lan_access,
        lan_https=lan_https,
        tunnel=tunnel,
    )

    service.set_reload_callback(lambda: {"reloaded": True, "pid": os.getpid()})

    assert service.current_host() == "0.0.0.0"
    assert service.reload() == {"reloaded": True, "pid": os.getpid()}


def test_console_network_reload_reports_fallback_without_callback(tmp_path):
    service = ConsoleNetworkService(
        nanobot_dir=tmp_path,
        port=6688,
        lan_access=SimpleNamespace(read_state=lambda: {"enabled": False}),
        lan_https=SimpleNamespace(ssl_paths=lambda: (None, None)),
        tunnel=SimpleNamespace(public_url=""),
    )

    result = service.reload()

    assert result["reloaded"] is False
    assert result["fallback"] == "no_callback"
    assert result["pid"] == os.getpid()
