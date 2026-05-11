from __future__ import annotations

from pathlib import Path


SERVICE_FILES = [
    Path("ava/console/services/tunnel_service.py"),
    Path("ava/console/services/lan_mdns_service.py"),
    Path("ava/console/services/lan_https_service.py"),
    Path("ava/console/services/pair_throttle_service.py"),
    Path("ava/console/services/console_network_service.py"),
    Path("ava/storage/lan_devices_store.py"),
]


def test_lan_access_services_do_not_import_nanobot_runtime():
    for path in SERVICE_FILES:
        source = path.read_text("utf-8")
        assert "import nanobot" not in source
        assert "from nanobot" not in source
