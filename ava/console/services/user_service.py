"""User management with file-based storage."""

from __future__ import annotations

import json
from datetime import datetime, timezone
from pathlib import Path

import bcrypt as _bcrypt

from ava.console.models import UserInfo


def _hash_password(password: str) -> str:
    return _bcrypt.hashpw(password.encode("utf-8"), _bcrypt.gensalt()).decode("utf-8")


def _verify_password(password: str, hashed: str) -> bool:
    return _bcrypt.checkpw(password.encode("utf-8"), hashed.encode("utf-8"))


class UserService:
    def __init__(self, console_dir: Path):
        self._file = console_dir / "users.json"
        console_dir.mkdir(parents=True, exist_ok=True)
        if not self._file.exists():
            self._save({})

    def _load(self) -> dict:
        return json.loads(self._file.read_text("utf-8")) if self._file.exists() else {}

    def _save(self, data: dict) -> None:
        self._file.write_text(json.dumps(data, indent=2, ensure_ascii=False), "utf-8")

    def list_users(self) -> list[UserInfo]:
        data = self._load()
        return [
            UserInfo(username=u, role=d["role"], created_at=d.get("created_at", ""))
            for u, d in data.items()
        ]

    def get_user(self, username: str) -> UserInfo | None:
        data = self._load()
        d = data.get(username)
        if not d:
            return None
        return UserInfo(username=username, role=d["role"], created_at=d.get("created_at", ""))

    def create_user(self, username: str, password: str, role: str) -> UserInfo:
        data = self._load()
        if username in data:
            raise ValueError(f"User '{username}' already exists")
        now = datetime.now(timezone.utc).isoformat()
        data[username] = {
            "password_hash": _hash_password(password),
            "role": role,
            "created_at": now,
        }
        self._save(data)
        return UserInfo(username=username, role=role, created_at=now)

    def update_user(self, username: str, password: str | None = None, role: str | None = None) -> UserInfo:
        data = self._load()
        if username not in data:
            raise ValueError(f"User '{username}' not found")
        if password:
            data[username]["password_hash"] = _hash_password(password)
        if role:
            data[username]["role"] = role
        self._save(data)
        return UserInfo(
            username=username,
            role=data[username]["role"],
            created_at=data[username].get("created_at", ""),
        )

    def delete_user(self, username: str) -> bool:
        data = self._load()
        if username not in data:
            return False
        del data[username]
        self._save(data)
        return True

    def verify_password(self, username: str, password: str) -> UserInfo | None:
        data = self._load()
        user_data = data.get(username)
        if not user_data:
            return None
        if not _verify_password(password, user_data["password_hash"]):
            return None
        return UserInfo(
            username=username,
            role=user_data["role"],
            created_at=user_data.get("created_at", ""),
        )

    def has_any_user(self) -> bool:
        return bool(self._load())

