"""SQLite-backed LAN device registry."""

from __future__ import annotations

import json
from datetime import datetime, timedelta, timezone
from typing import Any


MIGRATION_NAME = "lan_devices_from_json_v1"


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _json_list(value: Any, default: list[str] | None = None) -> str:
    if not isinstance(value, list):
        value = default or []
    return json.dumps(value, ensure_ascii=False)


class LanDevicesStore:
    def __init__(self, db):
        self._db = db

    def is_migrated(self) -> bool:
        row = self._db.fetchone(
            "SELECT name FROM schema_migrations WHERE name = ?",
            (MIGRATION_NAME,),
        )
        return row is not None

    def mark_migrated(self) -> None:
        self._db.execute(
            "INSERT OR IGNORE INTO schema_migrations (name, applied_at) VALUES (?, ?)",
            (MIGRATION_NAME, _now_iso()),
        )
        self._db.commit()

    def migrate_from_state(self, devices: list[dict[str, Any]]) -> int:
        if self.is_migrated():
            return 0
        count = 0
        for device in devices:
            device_id = str(device.get("device_id") or "")
            token_id = str(device.get("token_id") or "")
            if not device_id or not token_id:
                continue
            created_at = str(device.get("created_at") or _now_iso())
            try:
                default_expires_at = datetime.fromisoformat(created_at) + timedelta(days=30)
            except ValueError:
                default_expires_at = datetime.now(timezone.utc) + timedelta(days=30)
            expires_at = str(device.get("expires_at") or default_expires_at.isoformat())
            self.upsert({
                "device_id": device_id,
                "token_id": token_id,
                "name": str(device.get("name") or "LAN device"),
                "role": str(device.get("role") or "read_only"),
                "capabilities": device.get("capabilities") or ["read"],
                "created_at": created_at,
                "last_seen_at": str(device.get("last_seen_at") or created_at),
                "last_ip": str(device.get("last_ip") or ""),
                "user_agent": str(device.get("user_agent") or ""),
                "expires_at": expires_at,
                "revoked_at": device.get("revoked_at"),
            })
            count += 1
        self.mark_migrated()
        return count

    def list_devices(self) -> list[dict[str, Any]]:
        rows = self._db.fetchall(
            """
            SELECT device_id, token_id, name, role, capabilities, created_at,
                   last_seen_at, last_ip, user_agent, expires_at, revoked_at
              FROM lan_devices
             ORDER BY created_at DESC
            """
        )
        return [self._row_to_device(row) for row in rows]

    def get(self, device_id: str) -> dict[str, Any] | None:
        row = self._db.fetchone(
            """
            SELECT device_id, token_id, name, role, capabilities, created_at,
                   last_seen_at, last_ip, user_agent, expires_at, revoked_at
              FROM lan_devices
             WHERE device_id = ?
            """,
            (device_id,),
        )
        return self._row_to_device(row) if row else None

    def upsert(self, device: dict[str, Any]) -> None:
        self._db.execute(
            """
            INSERT INTO lan_devices (
                device_id, token_id, name, role, capabilities, created_at,
                last_seen_at, last_ip, user_agent, expires_at, revoked_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(device_id) DO UPDATE SET
                token_id = excluded.token_id,
                name = excluded.name,
                role = excluded.role,
                capabilities = excluded.capabilities,
                last_seen_at = excluded.last_seen_at,
                last_ip = excluded.last_ip,
                user_agent = excluded.user_agent,
                expires_at = excluded.expires_at,
                revoked_at = excluded.revoked_at
            """,
            (
                device["device_id"],
                device["token_id"],
                device.get("name") or "LAN device",
                device.get("role") or "read_only",
                _json_list(device.get("capabilities"), ["read"]),
                device.get("created_at") or _now_iso(),
                device.get("last_seen_at") or _now_iso(),
                device.get("last_ip") or "",
                device.get("user_agent") or "",
                device.get("expires_at") or _now_iso(),
                device.get("revoked_at"),
            ),
        )
        self._db.commit()

    def update_capabilities(self, device_id: str, capabilities: list[str]) -> dict[str, Any]:
        self._db.execute(
            "UPDATE lan_devices SET capabilities = ? WHERE device_id = ?",
            (_json_list(capabilities), device_id),
        )
        self._db.commit()
        device = self.get(device_id)
        if not device:
            raise KeyError(device_id)
        return device

    def update_expiry(self, device_id: str, expires_at: str) -> dict[str, Any]:
        self._db.execute(
            "UPDATE lan_devices SET expires_at = ? WHERE device_id = ?",
            (expires_at, device_id),
        )
        self._db.commit()
        device = self.get(device_id)
        if not device:
            raise KeyError(device_id)
        return device

    def revoke(self, device_id: str, revoked_at: str) -> dict[str, Any]:
        self._db.execute(
            "UPDATE lan_devices SET revoked_at = COALESCE(revoked_at, ?) WHERE device_id = ?",
            (revoked_at, device_id),
        )
        self._db.commit()
        device = self.get(device_id)
        if not device:
            raise KeyError(device_id)
        return device

    def mark_seen(self, device_id: str, *, last_seen_at: str, ip: str = "") -> None:
        self._db.execute(
            """
            UPDATE lan_devices
               SET last_seen_at = ?,
                   last_ip = CASE WHEN ? != '' THEN ? ELSE last_ip END
             WHERE device_id = ? AND revoked_at IS NULL
            """,
            (last_seen_at, ip, ip, device_id),
        )
        self._db.commit()

    def cleanup_expired(self, now_iso: str) -> int:
        rows = self._db.fetchall(
            "SELECT device_id FROM lan_devices WHERE revoked_at IS NULL AND expires_at <= ?",
            (now_iso,),
        )
        for row in rows:
            self._db.execute(
                "UPDATE lan_devices SET revoked_at = ? WHERE device_id = ?",
                (now_iso, row["device_id"]),
            )
        self._db.commit()
        return len(rows)

    def log_event(
        self,
        *,
        event: str,
        device_id: str = "",
        ip: str = "",
        user_agent: str = "",
        detail: dict[str, Any] | None = None,
    ) -> None:
        self._db.execute(
            """
            INSERT INTO lan_device_events (timestamp, device_id, event, ip, user_agent, detail)
            VALUES (?, ?, ?, ?, ?, ?)
            """,
            (
                _now_iso(),
                device_id,
                event,
                ip,
                user_agent,
                json.dumps(detail or {}, ensure_ascii=False),
            ),
        )
        self._db.commit()

    @staticmethod
    def _row_to_device(row) -> dict[str, Any]:
        capabilities: list[str]
        try:
            raw = json.loads(row["capabilities"] or "[]")
            capabilities = raw if isinstance(raw, list) else []
        except json.JSONDecodeError:
            capabilities = []
        return {
            "device_id": row["device_id"],
            "token_id": row["token_id"],
            "name": row["name"],
            "role": row["role"],
            "capabilities": [str(item) for item in capabilities],
            "created_at": row["created_at"],
            "last_seen_at": row["last_seen_at"],
            "last_ip": row["last_ip"] or "",
            "user_agent": row["user_agent"] or "",
            "expires_at": row["expires_at"],
            "revoked_at": row["revoked_at"],
        }
