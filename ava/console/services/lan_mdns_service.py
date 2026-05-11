"""mDNS advertisement for LAN Access."""

from __future__ import annotations

import socket
from dataclasses import dataclass


@dataclass
class MdnsStatus:
    running: bool
    name: str
    service_type: str = "_ava._tcp.local."
    error: str = ""


class LanMdnsService:
    def __init__(self, *, port: int, name: str = "Ava Console"):
        self._port = port
        self._name = name
        self._zeroconf = None
        self._service_info = None
        self._error = ""

    @property
    def running(self) -> bool:
        return self._zeroconf is not None

    def start(self) -> MdnsStatus:
        if self.running:
            return self.status()
        try:
            from zeroconf import IPVersion, ServiceInfo, Zeroconf
        except ImportError as exc:
            self._error = str(exc)
            return self.status()

        service_type = "_ava._tcp.local."
        service_name = f"{self._name}.{service_type}"
        addresses = [_socket_ip_bytes(ip) for ip in _local_ipv4_addresses()]
        if not addresses:
            addresses = [_socket_ip_bytes("127.0.0.1")]
        try:
            self._zeroconf = Zeroconf(ip_version=IPVersion.All)
            self._service_info = ServiceInfo(
                type_=service_type,
                name=service_name,
                addresses=addresses,
                port=self._port,
                properties={b"path": b"/lan/pair"},
                server="ava.local.",
            )
            self._zeroconf.register_service(self._service_info)
            self._error = ""
        except Exception as exc:
            if self._zeroconf is not None:
                self._zeroconf.close()
            self._zeroconf = None
            self._service_info = None
            self._error = str(exc)
        return self.status()

    def stop(self) -> MdnsStatus:
        if self._zeroconf is not None and self._service_info is not None:
            try:
                self._zeroconf.unregister_service(self._service_info)
            except Exception:
                pass
        if self._zeroconf is not None:
            self._zeroconf.close()
        self._zeroconf = None
        self._service_info = None
        return self.status()

    def status(self) -> MdnsStatus:
        return MdnsStatus(running=self.running, name=self._name, error=self._error)


def _socket_ip_bytes(ip: str) -> bytes:
    return socket.inet_aton(ip)


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
