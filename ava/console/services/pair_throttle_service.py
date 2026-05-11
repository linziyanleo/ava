"""Persistent throttle state for public LAN pairing."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timedelta, timezone


PAIR_IP_LIMIT = 10
PAIR_IP_WINDOW_SECONDS = 60
PAIR_PIN_FAILURE_LIMIT = 5
PAIR_LOCK_SECONDS = 10 * 60


def _now() -> datetime:
    return datetime.now(timezone.utc)


def _iso(ts: datetime) -> str:
    return ts.isoformat()


def _parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value)
    except ValueError:
        return None


@dataclass
class ThrottleDecision:
    allowed: bool
    locked_until: str | None = None
    reason: str = ""


class PairThrottleService:
    def __init__(self, db):
        self._db = db

    def check_ip(self, ip: str) -> ThrottleDecision:
        key = ip or "unknown"
        row = self._db.fetchone(
            "SELECT first_failed_at, failure_count, locked_until FROM lan_pair_throttle WHERE scope = 'ip' AND key = ?",
            (key,),
        )
        if not row:
            return ThrottleDecision(True)
        now = _now()
        locked_until = _parse_iso(row["locked_until"])
        if locked_until and locked_until > now:
            return ThrottleDecision(False, _iso(locked_until), "ip")
        first_failed_at = _parse_iso(row["first_failed_at"])
        if first_failed_at and now - first_failed_at > timedelta(seconds=PAIR_IP_WINDOW_SECONDS):
            return ThrottleDecision(True)
        if int(row["failure_count"]) >= PAIR_IP_LIMIT:
            locked = now + timedelta(seconds=PAIR_LOCK_SECONDS)
            self._lock("ip", key, locked)
            return ThrottleDecision(False, _iso(locked), "ip")
        return ThrottleDecision(True)

    def record_failure(self, *, ip: str, pin_hash: str) -> ThrottleDecision:
        now = _now()
        ip_decision = self._increment(
            scope="ip",
            key=ip or "unknown",
            now=now,
            limit=PAIR_IP_LIMIT,
            window_seconds=PAIR_IP_WINDOW_SECONDS,
        )
        pin_decision = self._increment(
            scope="pin",
            key=pin_hash or "unknown",
            now=now,
            limit=PAIR_PIN_FAILURE_LIMIT,
            window_seconds=None,
        )
        if not pin_decision.allowed:
            return pin_decision
        return ip_decision

    def reset_pin(self, pin_hash: str) -> None:
        self._db.execute(
            "DELETE FROM lan_pair_throttle WHERE scope = 'pin' AND key = ?",
            (pin_hash,),
        )
        self._db.commit()

    def cleanup_expired_lockouts(self) -> int:
        now_iso = _iso(_now())
        rows = self._db.fetchall(
            "SELECT scope, key FROM lan_pair_throttle WHERE locked_until IS NOT NULL AND locked_until <= ?",
            (now_iso,),
        )
        for row in rows:
            self._db.execute(
                "DELETE FROM lan_pair_throttle WHERE scope = ? AND key = ?",
                (row["scope"], row["key"]),
            )
        self._db.commit()
        return len(rows)

    def _increment(
        self,
        *,
        scope: str,
        key: str,
        now: datetime,
        limit: int,
        window_seconds: int | None,
    ) -> ThrottleDecision:
        row = self._db.fetchone(
            "SELECT first_failed_at, failure_count, locked_until FROM lan_pair_throttle WHERE scope = ? AND key = ?",
            (scope, key),
        )
        if row:
            locked_until = _parse_iso(row["locked_until"])
            if locked_until and locked_until > now:
                return ThrottleDecision(False, _iso(locked_until), scope)
            first_failed_at = _parse_iso(row["first_failed_at"])
            reset_window = (
                window_seconds is not None
                and first_failed_at is not None
                and now - first_failed_at > timedelta(seconds=window_seconds)
            )
            failure_count = 1 if reset_window else int(row["failure_count"]) + 1
            first_failed_at_value = now if reset_window else first_failed_at or now
        else:
            failure_count = 1
            first_failed_at_value = now

        locked_until = None
        allowed = True
        if failure_count >= limit:
            locked_until = now + timedelta(seconds=PAIR_LOCK_SECONDS)
            allowed = False
        self._db.execute(
            """
            INSERT INTO lan_pair_throttle
                (scope, key, first_failed_at, last_failed_at, failure_count, locked_until)
            VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(scope, key) DO UPDATE SET
                first_failed_at = excluded.first_failed_at,
                last_failed_at = excluded.last_failed_at,
                failure_count = excluded.failure_count,
                locked_until = excluded.locked_until
            """,
            (
                scope,
                key,
                _iso(first_failed_at_value),
                _iso(now),
                failure_count,
                _iso(locked_until) if locked_until else None,
            ),
        )
        self._db.commit()
        return ThrottleDecision(allowed, _iso(locked_until) if locked_until else None, scope)

    def _lock(self, scope: str, key: str, locked_until: datetime) -> None:
        self._db.execute(
            """
            UPDATE lan_pair_throttle
               SET locked_until = ?
             WHERE scope = ? AND key = ?
            """,
            (_iso(locked_until), scope, key),
        )
        self._db.commit()
