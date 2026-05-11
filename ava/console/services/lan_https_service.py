"""Self-signed CA and HTTPS certificate management for LAN Access."""

from __future__ import annotations

import ipaddress
import json
import socket
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path


HTTPS_STATE_KEY = "https"


@dataclass
class LanHttpsStatus:
    enabled: bool
    ca_certificate_path: str
    certificate_path: str
    key_path: str


class LanHttpsService:
    def __init__(self, nanobot_dir: Path):
        self._dir = nanobot_dir / "console"
        self._cert_dir = self._dir / "lan-certs"
        self._state_file = self._dir / "lan-access.json"

    @property
    def enabled(self) -> bool:
        return bool(self._read_state().get(HTTPS_STATE_KEY, {}).get("enabled"))

    def status(self) -> LanHttpsStatus:
        return LanHttpsStatus(
            enabled=self.enabled,
            ca_certificate_path=str(self.ca_certificate_path()),
            certificate_path=str(self.certificate_path()),
            key_path=str(self.key_path()),
        )

    def enable(self, *, tunnel_hostname: str = "") -> LanHttpsStatus:
        self._cert_dir.mkdir(parents=True, exist_ok=True)
        if not self.ca_certificate_path().exists() or not self.ca_key_path().exists():
            self._generate_ca()
        self._generate_leaf(tunnel_hostname=tunnel_hostname)
        state = self._read_state()
        state.setdefault(HTTPS_STATE_KEY, {})["enabled"] = True
        self._write_state(state)
        return self.status()

    def disable(self) -> LanHttpsStatus:
        state = self._read_state()
        state.setdefault(HTTPS_STATE_KEY, {})["enabled"] = False
        self._write_state(state)
        return self.status()

    def ssl_paths(self) -> tuple[str | None, str | None]:
        if not self.enabled:
            return None, None
        cert = self.certificate_path()
        key = self.key_path()
        if not cert.exists() or not key.exists():
            return None, None
        return str(cert), str(key)

    def ca_certificate_path(self) -> Path:
        return self._cert_dir / "ava-lan-ca.crt"

    def ca_key_path(self) -> Path:
        return self._cert_dir / "ava-lan-ca.key"

    def certificate_path(self) -> Path:
        return self._cert_dir / "ava-lan.crt"

    def key_path(self) -> Path:
        return self._cert_dir / "ava-lan.key"

    def _read_state(self) -> dict:
        if not self._state_file.exists():
            return {}
        try:
            data = json.loads(self._state_file.read_text("utf-8"))
        except (OSError, json.JSONDecodeError):
            return {}
        return data if isinstance(data, dict) else {}

    def _write_state(self, state: dict) -> None:
        self._dir.mkdir(parents=True, exist_ok=True)
        self._state_file.write_text(json.dumps(state, indent=2, ensure_ascii=False), encoding="utf-8")

    def _generate_ca(self) -> None:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        subject = issuer = x509.Name([
            x509.NameAttribute(NameOID.COMMON_NAME, "Ava LAN Access Local CA"),
        ])
        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(subject)
            .issuer_name(issuer)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=3650))
            .add_extension(x509.BasicConstraints(ca=True, path_length=None), critical=True)
            .sign(key, hashes.SHA256())
        )
        self.ca_key_path().write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
        self.ca_certificate_path().write_bytes(cert.public_bytes(serialization.Encoding.PEM))

    def _generate_leaf(self, *, tunnel_hostname: str = "") -> None:
        from cryptography import x509
        from cryptography.hazmat.primitives import hashes, serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from cryptography.x509.oid import NameOID

        ca_key = serialization.load_pem_private_key(self.ca_key_path().read_bytes(), password=None)
        ca_cert = x509.load_pem_x509_certificate(self.ca_certificate_path().read_bytes())
        key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        names: list[x509.GeneralName] = [
            x509.DNSName("localhost"),
            x509.DNSName("ava.local"),
            x509.IPAddress(ipaddress.ip_address("127.0.0.1")),
        ]
        for ip in _local_ipv4_addresses():
            names.append(x509.IPAddress(ipaddress.ip_address(ip)))
        if tunnel_hostname:
            names.append(x509.DNSName(tunnel_hostname))
        now = datetime.now(timezone.utc)
        cert = (
            x509.CertificateBuilder()
            .subject_name(x509.Name([x509.NameAttribute(NameOID.COMMON_NAME, "Ava LAN Access")]))
            .issuer_name(ca_cert.subject)
            .public_key(key.public_key())
            .serial_number(x509.random_serial_number())
            .not_valid_before(now - timedelta(minutes=1))
            .not_valid_after(now + timedelta(days=365))
            .add_extension(x509.SubjectAlternativeName(names), critical=False)
            .sign(ca_key, hashes.SHA256())
        )
        self.key_path().write_bytes(
            key.private_bytes(
                serialization.Encoding.PEM,
                serialization.PrivateFormat.TraditionalOpenSSL,
                serialization.NoEncryption(),
            )
        )
        self.certificate_path().write_bytes(cert.public_bytes(serialization.Encoding.PEM))


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
    return sorted(addresses)
