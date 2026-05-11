from __future__ import annotations

from ava.console.services.lan_mdns_service import LanMdnsService


def test_lan_mdns_stop_is_idempotent():
    service = LanMdnsService(port=6688)

    assert service.status().running is False
    stopped = service.stop()

    assert stopped.running is False
    assert stopped.service_type == "_ava._tcp.local."
