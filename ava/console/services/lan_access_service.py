"""LAN Access state, pairing, and device-token management."""

from __future__ import annotations

import hashlib
import json
import secrets
import socket
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode, urlparse

from ava.console import auth
from ava.storage.lan_devices_store import LanDevicesStore

LAN_ACCESS_STATE_FILE = "lan-access.json"
PAIRING_TTL_SECONDS = 5 * 60
DEVICE_TOKEN_TTL_DAYS = 30
VALID_CAPABILITIES = {"read", "review", "operate"}


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
        "https": {"enabled": False},
    }


def resolve_console_bind_host(nanobot_dir: Path, configured_host: str | None = None) -> str:
    state = LanAccessService(nanobot_dir).read_state()
    if state.get("enabled"):
        return "0.0.0.0"
    return "127.0.0.1"


class LanAccessService:
    def __init__(self, nanobot_dir: Path, *, console_port: int = 6688, db=None):
        self._dir = nanobot_dir / "console"
        self._state_file = self._dir / LAN_ACCESS_STATE_FILE
        self._console_port = console_port
        self._devices_store = LanDevicesStore(db) if db is not None else None

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
        data.setdefault("https", default["https"])
        return data

    def _write_state(self, state: dict[str, Any]) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    def migrate_devices_if_needed(self) -> int:
        if self._devices_store is None:
            return 0
        state = self.read_state()
        count = self._devices_store.migrate_from_state(state.get("devices", []))
        if count and self._state_file.exists():
            backup = self._state_file.with_suffix(".json.bak")
            if not backup.exists():
                backup.write_text(self._state_file.read_text("utf-8"), encoding="utf-8")
        return count

    def get_status(self) -> dict[str, Any]:
        state = self.read_state()
        enabled = bool(state.get("enabled"))
        devices = [self._public_device(item) for item in self._list_devices(enabled=enabled)]
        pairing = state.get("pairing") or {}
        expires_at = _parse_iso(pairing.get("expires_at"))
        pairing_active = bool(expires_at and expires_at > _now())

        return {
            "enabled": enabled,
            "bind_host": "0.0.0.0" if enabled else "127.0.0.1",
            "port": self._console_port,
            "lan_urls": self.get_lan_urls() if enabled else [],
            "pairing_active": pairing_active,
            "pairing_expires_at": pairing.get("expires_at") if pairing_active else None,
            "devices": devices,
            "https_enabled": bool((state.get("https") or {}).get("enabled")),
        }

    def set_enabled(self, enabled: bool) -> dict[str, Any]:
        state = self.read_state()
        state["enabled"] = bool(enabled)
        if not enabled:
            state["pairing"] = None
        self._write_state(state)
        if enabled:
            self.migrate_devices_if_needed()
            self.cleanup_expired_devices()
        return self.get_status()

    def create_pairing_pin(self, *, ttl_seconds: int = PAIRING_TTL_SECONDS) -> dict[str, Any]:
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
        pairing_url = self.qr_payload(pin)["url"]
        return {
            "pin": pin,
            "expires_at": _iso(expires_at),
            "pairing_url": pairing_url,
            "qr_payload": pairing_url,
        }

    def qr_payload(self, pin: str) -> dict[str, str]:
        base_url = self.get_lan_urls()[0] if self.get_lan_urls() else f"http://127.0.0.1:{self._console_port}/"
        return {"url": f"{base_url.rstrip('/')}/lan/pair?{urlencode({'pin': pin})}"}

    def current_pairing_hash(self) -> str:
        pairing = self.read_state().get("pairing") or {}
        return str(pairing.get("pin_hash") or "")

    def invalidate_pin(self, reason: str = "") -> None:
        state = self.read_state()
        state["pairing"] = None
        self._write_state(state)

    def burn_pairing_pin(self) -> None:
        self.invalidate_pin("burned")

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
        token_expires_at = _iso(_now() + timedelta(days=DEVICE_TOKEN_TTL_DAYS))
        capabilities = ["read"]
        device = {
            "device_id": device_id,
            "token_id": token_id,
            "name": device_name or "LAN device",
            "role": "read_only",
            "capabilities": capabilities,
            "created_at": created_at,
            "last_seen_at": created_at,
            "last_ip": ip,
            "user_agent": user_agent,
            "expires_at": token_expires_at,
            "revoked_at": None,
        }
        if self._devices_store is not None:
            self.migrate_devices_if_needed()
            self._devices_store.upsert(device)
            self._devices_store.log_event(
                event="paired",
                device_id=device_id,
                ip=ip,
                user_agent=user_agent,
                detail={"name": device["name"]},
            )
        else:
            state["devices"].append(device)
        state["pairing"] = None
        self._write_state(state)

        token = auth.create_access_token(
            {
                "sub": f"device:{device_id}",
                "role": "read_only",
                "created_at": created_at,
                "kind": "device",
                "device_id": device_id,
                "token_id": token_id,
                "capabilities": capabilities,
                "expires_at": token_expires_at,
            },
            expires_delta=timedelta(days=DEVICE_TOKEN_TTL_DAYS),
        )
        return {"access_token": token, "token_type": "bearer", "device": self._public_device(device)}

    def update_device_capabilities(self, device_id: str, capabilities: list[str]) -> dict[str, Any]:
        invalid = sorted(set(capabilities) - VALID_CAPABILITIES)
        if invalid:
            raise ValueError(f"Invalid capabilities: {', '.join(invalid)}")
        normalized = [cap for cap in ("read", "review", "operate") if cap in set(capabilities)]
        if self._devices_store is None:
            state = self.read_state()
            for device in state.get("devices", []):
                if device.get("device_id") == device_id:
                    device["capabilities"] = normalized
                    self._write_state(state)
                    return self._public_device(device)
            raise KeyError(device_id)
        self.migrate_devices_if_needed()
        device = self._devices_store.update_capabilities(device_id, normalized)
        self._devices_store.log_event(
            event="capability_update",
            device_id=device_id,
            detail={"capabilities": normalized},
        )
        return self._public_device(device)

    def bump_capabilities(self, device_id: str, capabilities: list[str], actor: str = "") -> dict[str, Any]:
        return self.update_device_capabilities(device_id, capabilities)

    def renew_device(self, device_id: str, *, ttl_days: int = DEVICE_TOKEN_TTL_DAYS) -> dict[str, Any]:
        expires_at = _iso(_now() + timedelta(days=ttl_days))
        if self._devices_store is None:
            state = self.read_state()
            for device in state.get("devices", []):
                if device.get("device_id") == device_id:
                    device["expires_at"] = expires_at
                    self._write_state(state)
                    return self._public_device(device)
            raise KeyError(device_id)
        self.migrate_devices_if_needed()
        device = self._devices_store.update_expiry(device_id, expires_at)
        self._devices_store.log_event(
            event="renew",
            device_id=device_id,
            detail={"expires_at": expires_at},
        )
        return self._public_device(device)

    def cleanup_expired_devices(self) -> int:
        if self._devices_store is None:
            return 0
        self.migrate_devices_if_needed()
        return self._devices_store.cleanup_expired(_iso())

    def revoke_device(self, device_id: str) -> dict[str, Any]:
        revoked_at = _iso()
        if self._devices_store is not None:
            self.migrate_devices_if_needed()
            return self._public_device(self._devices_store.revoke(device_id, revoked_at))
        state = self.read_state()
        found = None
        for device in state.get("devices", []):
            if device.get("device_id") == device_id:
                device["revoked_at"] = device.get("revoked_at") or revoked_at
                found = device
                break
        if found is None:
            raise KeyError(device_id)
        self._write_state(state)
        return self._public_device(found)

    def validate_device_token(self, payload: dict[str, Any]) -> bool:
        if not self.read_state().get("enabled"):
            return False
        device_id = payload.get("device_id")
        token_id = payload.get("token_id")
        if not device_id or not token_id:
            return False
        device = self._find_device(str(device_id))
        if not device or device.get("token_id") != token_id or device.get("revoked_at"):
            return False
        expires_at = _parse_iso(device.get("expires_at"))
        return bool(expires_at and expires_at > _now())

    def mark_device_seen(self, device_id: str, *, ip: str = "") -> None:
        if self._devices_store is not None:
            self._devices_store.mark_seen(device_id, last_seen_at=_iso(), ip=ip)
            return
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

    def log_pair_failure(
        self,
        *,
        event: str,
        ip: str,
        user_agent: str,
        pin_hash: str,
        reason: str,
    ) -> None:
        if self._devices_store is None:
            return
        self._devices_store.log_event(
            event=event,
            ip=ip,
            user_agent=user_agent,
            detail={"pin_hash": pin_hash, "reason": reason},
        )

    def get_lan_urls(self) -> list[str]:
        urls: list[str] = []
        scheme = "https" if bool((self.read_state().get("https") or {}).get("enabled")) else "http"
        for ip in _local_ipv4_addresses():
            urls.append(f"{scheme}://{ip}:{self._console_port}/")
        return urls

    def allowed_lan_origins(self) -> set[str]:
        origins = {
            f"http://127.0.0.1:{self._console_port}",
            f"http://localhost:{self._console_port}",
        }
        if bool((self.read_state().get("https") or {}).get("enabled")):
            origins.update({
                f"https://127.0.0.1:{self._console_port}",
                f"https://localhost:{self._console_port}",
            })
        for url in self.get_lan_urls():
            parsed = urlparse(url)
            if parsed.scheme and parsed.netloc:
                origins.add(f"{parsed.scheme}://{parsed.netloc}")
        return origins

    def _list_devices(self, *, enabled: bool) -> list[dict[str, Any]]:
        if self._devices_store is None:
            return self.read_state().get("devices", [])
        if enabled:
            self.migrate_devices_if_needed()
        if not self._devices_store.is_migrated():
            return []
        return self._devices_store.list_devices()

    def _find_device(self, device_id: str) -> dict[str, Any] | None:
        if self._devices_store is not None:
            self.migrate_devices_if_needed()
            return self._devices_store.get(device_id)
        for device in self.read_state().get("devices", []):
            if device.get("device_id") == device_id:
                return device
        return None

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
            "user_agent": device.get("user_agent", ""),
            "expires_at": device.get("expires_at", ""),
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
