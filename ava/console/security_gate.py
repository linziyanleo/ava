"""Console security gate (production-path)."""

from __future__ import annotations

from typing import Any

DEFAULT_CONSOLE_SECRET = "change-me-in-production-use-a-longer-key!"


def validate_console_security(console_cfg: Any, console_host: str) -> None:
    if not bool(getattr(console_cfg, "public_dev", False)):
        return

    secret_key = str(getattr(console_cfg, "secret_key", "") or "")
    if secret_key == DEFAULT_CONSOLE_SECRET or len(secret_key) < 32:
        raise RuntimeError("gateway.console.public_dev=true requires a strong secretKey")

    expire_minutes = int(getattr(console_cfg, "token_expire_minutes", 0) or 0)
    if expire_minutes <= 0 or expire_minutes > 60:
        raise RuntimeError("gateway.console.public_dev=true requires tokenExpireMinutes <= 60")

    if console_host not in {"127.0.0.1", "localhost", "::1"}:
        raise RuntimeError("gateway.console.public_dev=true only allows localhost origin binding")

    if not bool(getattr(console_cfg, "session_cookie_secure", False)):
        raise RuntimeError("gateway.console.public_dev=true requires secure session cookie")

    if not str(getattr(console_cfg, "cloudflare_access_team_domain", "") or "").strip():
        raise RuntimeError("gateway.console.public_dev=true requires cloudflareAccessTeamDomain")

    if not str(getattr(console_cfg, "cloudflare_access_audience", "") or "").strip():
        raise RuntimeError("gateway.console.public_dev=true requires cloudflareAccessAudience")
