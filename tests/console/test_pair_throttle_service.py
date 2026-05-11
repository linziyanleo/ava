from __future__ import annotations

from ava.console.services.pair_throttle_service import PAIR_PIN_FAILURE_LIMIT, PairThrottleService
from ava.storage import Database


def test_pair_throttle_persists_pin_lockout(tmp_path):
    db = Database(tmp_path / "ava.db")
    throttle = PairThrottleService(db)

    decision = None
    for _ in range(PAIR_PIN_FAILURE_LIMIT):
        decision = throttle.record_failure(ip="203.0.113.1", pin_hash="pin-hash")

    assert decision is not None
    assert decision.allowed is False
    assert decision.reason == "pin"
    assert decision.locked_until

    second = PairThrottleService(Database(tmp_path / "ava.db"))
    assert second.record_failure(ip="203.0.113.1", pin_hash="pin-hash").allowed is False


def test_pair_throttle_limits_ip_window(tmp_path):
    db = Database(tmp_path / "ava.db")
    throttle = PairThrottleService(db)

    for i in range(10):
        decision = throttle.record_failure(ip="203.0.113.9", pin_hash=f"pin-{i}")

    assert decision.allowed is False
    assert decision.reason == "ip"
    assert throttle.check_ip("203.0.113.9").allowed is False
