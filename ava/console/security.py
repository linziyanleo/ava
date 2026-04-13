"""Sensitive field masking for config files."""

from __future__ import annotations

import copy
import re

SENSITIVE_FIELD_NAMES = {
    "token", "api_key", "apiKey", "app_secret", "appSecret",
    "client_secret", "clientSecret", "encrypt_key", "encryptKey",
    "verification_token", "verificationToken", "bot_token", "botToken",
    "app_token", "appToken", "claw_token", "clawToken", "secret",
    "imap_password", "imapPassword", "smtp_password", "smtpPassword",
    "access_token", "accessToken", "bridge_token", "bridgeToken",
    "user_token_read_only",
}

_CAMEL_TO_SNAKE = re.compile(r"(?<=[a-z0-9])(?=[A-Z])")


def _is_sensitive_key(key: str) -> bool:
    normalized = _CAMEL_TO_SNAKE.sub("_", key).lower()
    return key in SENSITIVE_FIELD_NAMES or normalized in {
        k.lower() for k in SENSITIVE_FIELD_NAMES
    }


def mask_value(value: str) -> str:
    if not value or len(value) < 6:
        return "****" if value else ""
    return value[:4] + "****" + value[-2:]


def mask_config(config: dict) -> dict:
    """Deep-copy config and mask all sensitive string values."""
    result = copy.deepcopy(config)
    _mask_recursive(result)
    return result


def _mask_recursive(obj: dict | list, parent_key: str = "") -> None:
    if isinstance(obj, dict):
        for key, value in obj.items():
            if isinstance(value, str) and value and _is_sensitive_key(key):
                obj[key] = mask_value(value)
            elif isinstance(value, (dict, list)):
                _mask_recursive(value, key)
    elif isinstance(obj, list):
        for item in obj:
            if isinstance(item, (dict, list)):
                _mask_recursive(item, parent_key)


def reveal_field(config: dict, field_path: str) -> str | None:
    """Retrieve the raw value at a dot-separated JSON path."""
    parts = field_path.split(".")
    current = config
    for part in parts:
        if isinstance(current, dict) and part in current:
            current = current[part]
        else:
            return None
    return current if isinstance(current, str) else None
