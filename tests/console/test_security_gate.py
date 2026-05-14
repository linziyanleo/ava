"""Console security gate tests (migrated from test_mock_bundle_runtime.py)."""

from __future__ import annotations

from types import SimpleNamespace

import pytest

from ava.console.security_gate import validate_console_security


@pytest.mark.parametrize(
    ("secret_key", "expire_minutes", "host", "cookie_secure", "team_domain", "audience", "expected"),
    [
        ("short", 60, "127.0.0.1", True, "example.cloudflareaccess.com", "aud", "secretKey"),
        ("x" * 32, 120, "127.0.0.1", True, "example.cloudflareaccess.com", "aud", "tokenExpireMinutes"),
        ("x" * 32, 60, "0.0.0.0", True, "example.cloudflareaccess.com", "aud", "localhost origin"),
        ("x" * 32, 60, "127.0.0.1", False, "example.cloudflareaccess.com", "aud", "secure session cookie"),
        ("x" * 32, 60, "127.0.0.1", True, "", "aud", "cloudflareAccessTeamDomain"),
        ("x" * 32, 60, "127.0.0.1", True, "example.cloudflareaccess.com", "", "cloudflareAccessAudience"),
    ],
)
def test_validate_console_security_rejects_unsafe_public_dev(
    secret_key,
    expire_minutes,
    host,
    cookie_secure,
    team_domain,
    audience,
    expected,
):
    cfg = SimpleNamespace(
        public_dev=True,
        secret_key=secret_key,
        token_expire_minutes=expire_minutes,
        session_cookie_secure=cookie_secure,
        cloudflare_access_team_domain=team_domain,
        cloudflare_access_audience=audience,
    )

    with pytest.raises(RuntimeError, match=expected):
        validate_console_security(cfg, host)


def test_validate_console_security_accepts_safe_public_dev():
    cfg = SimpleNamespace(
        public_dev=True,
        secret_key="x" * 48,
        token_expire_minutes=60,
        session_cookie_secure=True,
        cloudflare_access_team_domain="example.cloudflareaccess.com",
        cloudflare_access_audience="test-audience",
    )

    validate_console_security(cfg, "127.0.0.1")


def test_validate_console_security_skips_when_public_dev_disabled():
    cfg = SimpleNamespace(public_dev=False, secret_key="short")
    validate_console_security(cfg, "0.0.0.0")
