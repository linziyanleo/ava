"""Local SQLite storage layer for nanobot."""

from ava.storage.database import Database

__all__ = ["Database", "get_db", "set_db"]

_db_instance: Database | None = None


def set_db(db: Database) -> None:
    """Register the global Database singleton (called by storage_patch)."""
    global _db_instance
    _db_instance = db


def get_db() -> Database | None:
    """Return the global Database singleton, or None if not yet initialized."""
    return _db_instance
