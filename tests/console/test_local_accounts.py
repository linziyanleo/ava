"""Tests for owner-only local account bootstrap and legacy migration."""

from __future__ import annotations

import json

from ava.console.local_accounts import (
    LOCAL_OWNER_PASSWORD_FILE,
    LOCAL_OWNER_USERNAME,
    ensure_local_accounts,
    migrate_users_json_to_owner,
)
from ava.console.services.user_service import UserService


def _write_users_json(console_dir, payload: dict) -> None:
    console_dir.mkdir(parents=True, exist_ok=True)
    (console_dir / "users.json").write_text(
        json.dumps(payload, indent=2, ensure_ascii=False), "utf-8"
    )


def test_migrate_users_json_to_owner_noop_when_file_missing(tmp_path):
    console_dir = tmp_path / "console"
    console_dir.mkdir()

    migrate_users_json_to_owner(console_dir)

    assert not (console_dir / "users.json").exists()


def test_migrate_users_json_to_owner_renames_single_admin(tmp_path):
    console_dir = tmp_path / "console"
    _write_users_json(
        console_dir,
        {
            "admin": {
                "password_hash": "$2b$hash-admin",
                "role": "admin",
                "created_at": "2026-01-01T00:00:00+00:00",
            },
        },
    )

    migrate_users_json_to_owner(console_dir)

    data = json.loads((console_dir / "users.json").read_text("utf-8"))
    assert list(data.keys()) == [LOCAL_OWNER_USERNAME]
    assert data[LOCAL_OWNER_USERNAME]["role"] == "owner"
    assert data[LOCAL_OWNER_USERNAME]["password_hash"] == "$2b$hash-admin"
    assert data[LOCAL_OWNER_USERNAME]["created_at"] == "2026-01-01T00:00:00+00:00"


def test_migrate_users_json_to_owner_collapses_multi_entry_using_admin_password(tmp_path):
    console_dir = tmp_path / "console"
    _write_users_json(
        console_dir,
        {
            "admin": {
                "password_hash": "$2b$hash-admin",
                "role": "admin",
                "created_at": "2026-02-01T00:00:00+00:00",
            },
            "editor1": {
                "password_hash": "$2b$hash-editor",
                "role": "editor",
                "created_at": "2026-01-01T00:00:00+00:00",
            },
            "viewer1": {
                "password_hash": "$2b$hash-viewer",
                "role": "viewer",
                "created_at": "2026-03-01T00:00:00+00:00",
            },
        },
    )

    migrate_users_json_to_owner(console_dir)

    data = json.loads((console_dir / "users.json").read_text("utf-8"))
    assert list(data.keys()) == [LOCAL_OWNER_USERNAME]
    assert data[LOCAL_OWNER_USERNAME]["password_hash"] == "$2b$hash-admin"


def test_migrate_users_json_to_owner_falls_back_to_earliest_created_at(tmp_path):
    console_dir = tmp_path / "console"
    _write_users_json(
        console_dir,
        {
            "editor1": {
                "password_hash": "$2b$hash-editor",
                "role": "editor",
                "created_at": "2026-01-01T00:00:00+00:00",
            },
            "viewer1": {
                "password_hash": "$2b$hash-viewer",
                "role": "viewer",
                "created_at": "2026-03-01T00:00:00+00:00",
            },
        },
    )

    migrate_users_json_to_owner(console_dir)

    data = json.loads((console_dir / "users.json").read_text("utf-8"))
    assert list(data.keys()) == [LOCAL_OWNER_USERNAME]
    assert data[LOCAL_OWNER_USERNAME]["password_hash"] == "$2b$hash-editor"


def test_ensure_local_accounts_creates_single_owner(tmp_path):
    console_dir = tmp_path / "console"
    users = UserService(console_dir)

    info = ensure_local_accounts(users, console_dir)

    assert info.username == LOCAL_OWNER_USERNAME
    assert info.role == "owner"
    assert (console_dir / "local-secrets" / LOCAL_OWNER_PASSWORD_FILE).is_file()
    assert users.get_user(LOCAL_OWNER_USERNAME) is not None
    assert users.get_user(LOCAL_OWNER_USERNAME).role == "owner"
    assert len(users.list_users()) == 1
