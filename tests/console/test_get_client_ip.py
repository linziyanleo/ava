from __future__ import annotations

from types import SimpleNamespace

from ava.console.middleware import get_client_ip


def _request(host: str, headers: dict[str, str]):
    return SimpleNamespace(client=SimpleNamespace(host=host), headers=headers)


def test_get_client_ip_trusts_cf_header_only_from_loopback_tunnel(monkeypatch):
    services = SimpleNamespace(tunnel=SimpleNamespace(running=True))
    monkeypatch.setattr("ava.console.app.get_services", lambda: services)

    assert get_client_ip(_request("127.0.0.1", {"cf-connecting-ip": "203.0.113.10"})) == "203.0.113.10"
    assert get_client_ip(_request("198.51.100.2", {"cf-connecting-ip": "203.0.113.10"})) == "198.51.100.2"
    assert get_client_ip(_request("127.0.0.1", {"x-forwarded-for": "203.0.113.12"})) == "127.0.0.1"


def test_get_client_ip_ignores_forwarded_headers_without_tunnel(monkeypatch):
    services = SimpleNamespace(tunnel=SimpleNamespace(running=False))
    monkeypatch.setattr("ava.console.app.get_services", lambda: services)

    request = _request("198.51.100.2", {
        "x-forwarded-for": "203.0.113.10",
        "cf-connecting-ip": "203.0.113.11",
    })
    assert get_client_ip(request) == "198.51.100.2"
