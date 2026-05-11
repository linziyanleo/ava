from __future__ import annotations

from cryptography import x509

from ava.console.services.lan_https_service import LanHttpsService


def test_lan_https_service_generates_ca_and_leaf_with_sans(tmp_path):
    service = LanHttpsService(tmp_path)

    status = service.enable(tunnel_hostname="example.trycloudflare.com")

    assert status.enabled is True
    assert service.ca_certificate_path().exists()
    assert service.certificate_path().exists()
    assert service.key_path().exists()
    cert = x509.load_pem_x509_certificate(service.certificate_path().read_bytes())
    san = cert.extensions.get_extension_for_class(x509.SubjectAlternativeName).value
    names = san.get_values_for_type(x509.DNSName)
    assert "localhost" in names
    assert "ava.local" in names
    assert "example.trycloudflare.com" in names
    assert service.disable().enabled is False
