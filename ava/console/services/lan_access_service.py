"""LAN Access state, pairing, and device-token management."""

from __future__ import annotations

import hashlib
import json
import secrets
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any

from ava.console import auth

LAN_ACCESS_STATE_FILE = "lan-access.json"
PAIRING_TTL_SECONDS = 5 * 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: datetime | None = None) -> str:
    return (ts or _now()).isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


def _hash_pin(pin: str, salt: str) -> str:
    return hashlib.sha256(f"{salt}:{pin}".encode("utf-8")).hexdigest()


def _default_state() -> dict[str, Any]:
    return {
        "enabled": False,
        "pairing": None,
        "devices": [],
    }


def resolve_console_bind_host(nanobot_dir: Path, configured_host: str | None = None) -> str:
    state = LanAccessService(nanobot_dir).read_state()
    if state.get("enabled"):
        return "0.0.0.0"
    return "127.0.0.1"


class LanAccessService:
    def __init__(self, nanobot_dir: Path, *, console_port: int = 6688):
        self._dir = nanobot_dir / "console"
        self._state_file = self._dir / LAN_ACCESS_STATE_FILE
        self._console_port = console_port

    def read_state(self) -> dict[str, Any]:
        if not self._state_file.exists():
            return _default_state()
        try:
            data = json.loads(self._state_file.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return _default_state()
        return self._normalize_state(data)

    def _normalize_state(self, data: dict[str, Any]) -> dict[str, Any]:
        default = _default_state()
        data.setdefault("enabled", default["enabled"])
        data.setdefault("pairing", default["pairing"])
        data.setdefault("devices", default["devices"])
        return data

    def _write_state(self, state: dict[str, Any]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    def get_status(self) -> dict[str, Any]:
        state = self.read_state()
        enabled = bool(state.get("enabled"))
        devices = [self._public_device(item) for item in state.get("devices", [])]
        pairing = state.get("pairing") or {}
        expires_at = _parse_iso(pairing.get("expires_at"))
        pairing_active = bool(expires_at and expires_at > _now())

        return {
            "enabled": enabled,
            "bind_host": "0.0.0.0" if enabled else "127.0.0.1",
            "port": self._console_port,
            "lan_urls": self._lan_urls() if enabled else [],
            "pairing_active": pairing_active,
            "pairing_expires_at": pairing.get("expires_at") if pairing_active else None,
            "devices": devices,
        }

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        state = self.read_state()
        state["enabled"] = bool(enabled)
        if not enabled:
            state["pairing"] = None
        self._write_state(state)
        return self.get_status()

    def create_pairing_pin(self, *, ttl_seconds: int = PAIRING_TTL_SECONDS) -> dict[str, str]:
        state = self.read_state()
        if not state.get("enabled"):
            raise ValueError("LAN Access is disabled")

        pin = f"{secrets.randbelow(1_000_000):06d}"
        salt = secrets.token_hex(8)
        expires_at = _now() + timedelta(seconds=ttl_seconds)
        state["pairing"] = {
            "pin_hash": _hash_pin(pin, salt),
            "salt": salt,
            "expires_at": _iso(expires_at),
            "created_at": _iso(),
        }
        self._write_state(state)
        return {
            "pin": pin,
            "expires_at": _iso(expires_at),
        }

    def pair_device(self, *, pin: str, device_name: str, ip: str = "", user_agent: str = "") -> dict[str, Any]:
        state = self.read_state()
        if not state.get("enabled"):
            raise ValueError("LAN Access is disabled")

        pairing = state.get("pairing") or {}
        expires_at = _parse_iso(pairing.get("expires_at"))
        if not expires_at or expires_at <= _now():
            raise ValueError("Pairing PIN expired")
        salt = pairing.get("salt") or ""
        if _hash_pin(pin, salt) != pairing.get("pin_hash"):
            raise ValueError("Invalid pairing PIN")

        device_id = secrets.token_hex(8)
        token_id = secrets.token_hex(16)
        created_at = _iso()
        device = {
            "device_id": device_id,
            "token_id": token_id,
            "name": device_name or "LAN device",
            "role": "read_only",
            "capabilities": ["read"],
            "created_at": created_at,
            "last_seen_at": created_at,
            "last_ip": ip,
            "user_agent": user_agent,
            "revoked_at": None,
        }
        state["devices"].append(device)
        state["pairing"] = None
        self._write_state(state)

        token = auth.create_access_token({
            "sub": f"device:{device_id}",
            "role": "read_only",
            "created_at": created_at,
            "kind": "device",
            "device_id": device_id,
            "token_id": token_id,
            "capabilities": ["read"],
        })
        return {"access_token": token, "token_type": "bearer", "device": self._public_device(device)}

    def revoke_device(self, device_id: str) -> dict[str, Any]:
        state = self.read_state()
        found = None
        for device in state.get("devices", []):
            if device.get("device_id") == device_id:
                device["revoked_at"] = device.get("revoked_at") or _iso()
                found = device
                break
        if found is None:
            raise KeyError(device_id)
        self._write_state(state)
        return self._public_device(found)

    def validate_device_token(self, payload: dict[str, Any]) -> bool:
        device_id = payload.get("device_id")
        token_id = payload.get("token_id")
        if not device_id or not token_id:
            return False
        for device in self.read_state().get("devices", []):
            if device.get("device_id") == device_id and device.get("token_id") == token_id:
                return not device.get("revoked_at")
        return False

    def mark_device_seen(self, device_id: str, *, ip: str = "") -> None:
        state = self.read_state()
        changed = False
        for device in state.get("devices", []):
            if device.get("device_id") == device_id and not device.get("revoked_at"):
                device["last_seen_at"] = _iso()
                if ip:
                    device["last_ip"] = ip
                changed = True
                break
        if changed:
            self._write_state(state)

    def _lan_urls(self) -> list[str]:
        urls: list[str] = []
        for ip in _local_ipv4_addresses():
            urls.append(f"http://{ip}:{self._console_port}/")
        return urls

    @staticmethod
    def _public_device(device: dict[str, Any]) -> dict[str, Any]:
        return {
            "device_id": device.get("device_id", ""),
            "name": device.get("name", ""),
            "role": device.get("role", "read_only"),
            "capabilities": device.get("capabilities", ["read"]),
            "created_at": device.get("created_at", ""),
            "last_seen_at": device.get("last_seen_at", ""),
            "last_ip": device.get("last_ip", ""),
            "revoked_at": device.get("revoked_at"),
        }


def _local_ipv4_addresses() -> list[str]:
    addresses: set[str] = set()
    try:
        hostname = socket.gethostname()
        for info in socket.getaddrinfo(hostname, None, socket.AF_INET, socket.SOCK_DGRAM):
            ip = info[4][0]
            if ip and not ip.startswith("127."):
                addresses.add(ip)
    except OSError:
        pass

    try:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        try:
            sock.connect(("8.8.8.8", 80))
            ip = sock.getsockname()[0]
            if ip and not ip.startswith("127."):
                addresses.add(ip)
        finally:
            sock.close()
    except OSError:
        pass
    return sorted(addresses)
