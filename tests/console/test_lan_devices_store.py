from __future__ import annotations

from datetime import datetime, timezone

from ava.storage.lan_devices_store import LanDevicesStore
from ava.storage import Database


def test_lan_devices_store_migrates_legacy_json_once(tmp_path):
    db = Database(tmp_path / "ava.db")
    store = LanDevicesStore(db)
    created_at = datetime.now(timezone.utc).isoformat()

    count = store.migrate_from_state([
        {
            "device_id": "phone",
            "token_id": "tok",
            "name": "phone",
            "role": "read_only",
            "capabilities": ["read"],
            "created_at": created_at,
            "last_seen_at": created_at,
            "last_ip": "192.168.1.2",
            "user_agent": "mobile",
            "revoked_at": None,
        }
    ])

    assert count == 1
    assert store.is_migrated() is True
    assert store.list_devices()[0]["device_id"] == "phone"
    assert store.list_devices()[0]["expires_at"] > created_at
    assert store.migrate_from_state([]) == 0
    assert len(store.list_devices()) == 1
