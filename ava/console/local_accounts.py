"""Single-owner local account bootstrap (post-mock-channel)."""

from __future__ import annotations

import json
import secrets
from dataclasses import dataclass
from pathlib import Path

LOCAL_OWNER_USERNAME = "owner"
LOCAL_OWNER_PASSWORD_FILE = "owner_password"
LOCAL_SECRETS_DIRNAME = "local-secrets"


@dataclass
class LocalAccountInfo:
    username: str
    role: str
    password_file: Path


def local_secrets_dir(console_dir: Path) -> Path:
    return console_dir / LOCAL_SECRETS_DIRNAME


def migrate_users_json_to_owner(console_dir: Path) -> None:
    """Collapse legacy users.json entries down to a single `owner` row.

    Must run before UserService is instantiated so legacy roles
    (admin/editor/viewer/read_only/mock_tester) never reach the
    ``UserInfoRole = Literal["owner", "read_only"]`` Pydantic check.

    Resolution policy:
      - Prefer the legacy ``admin`` entry's password_hash + created_at.
      - Otherwise fall back to the entry with the earliest ``created_at``.
      - File missing or empty: no-op.
    """
    users_file = console_dir / "users.json"
    if not users_file.exists():
        return

    raw = users_file.read_text("utf-8").strip()
    if not raw:
        return

    data = json.loads(raw)
    if not isinstance(data, dict) or not data:
        return

    if list(data.keys()) == [LOCAL_OWNER_USERNAME] and data[LOCAL_OWNER_USERNAME].get("role") == "owner":
        return

    chosen: dict | None = data.get("admin")
    if chosen is None:
        chosen = min(
            data.values(),
            key=lambda entry: str(entry.get("created_at", "")) or "￿",
        )

    collapsed = {
        LOCAL_OWNER_USERNAME: {
            "password_hash": chosen["password_hash"],
            "role": "owner",
            "created_at": chosen.get("created_at", ""),
        }
    }
    users_file.write_text(json.dumps(collapsed, indent=2, ensure_ascii=False), "utf-8")


def _ensure_password_file(path: Path, default_password: str | None = None) -> str:
    if path.exists():
        password = path.read_text("utf-8").strip()
        if password:
            return password

    password = default_password if default_password is not None else secrets.token_urlsafe(24)
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(password + "\n", "utf-8")
    try:
        path.chmod(0o600)
    except OSError:
        pass
    return password


def ensure_local_accounts(users, console_dir: Path) -> LocalAccountInfo:
    secrets_dir = local_secrets_dir(console_dir)
    secrets_dir.mkdir(parents=True, exist_ok=True)
    try:
        secrets_dir.chmod(0o700)
    except OSError:
        pass

    password_file = secrets_dir / LOCAL_OWNER_PASSWORD_FILE
    password = _ensure_password_file(password_file)

    existing = users.get_user(LOCAL_OWNER_USERNAME)
    if existing is None:
        users.create_user(LOCAL_OWNER_USERNAME, password, "owner")
    else:
        password_matches = users.verify_password(LOCAL_OWNER_USERNAME, password) is not None
        needs_role = existing.role != "owner"
        if not password_matches or needs_role:
            users.update_user(
                LOCAL_OWNER_USERNAME,
                password=password if not password_matches else None,
                role="owner" if needs_role else None,
            )

    return LocalAccountInfo(
        username=LOCAL_OWNER_USERNAME,
        role="owner",
        password_file=password_file,
    )
