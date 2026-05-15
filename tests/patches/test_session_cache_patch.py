"""Tests for session_cache_patch — EvictingSessionCache."""

import time
from unittest.mock import MagicMock, call

import pytest

from ava.patches.session_cache_patch import EvictingSessionCache


@pytest.fixture
def saved_keys():
    return []


@pytest.fixture
def make_session():
    def _make(key: str):
        s = MagicMock()
        s.key = key
        return s
    return _make


@pytest.fixture
def cache(saved_keys, make_session):
    def save_fn(session):
        saved_keys.append(session.key)
    return EvictingSessionCache(save_fn, maxsize=3, idle_timeout=0.5)


class TestEvictingSessionCache:
    def test_basic_set_get(self, cache, make_session):
        s = make_session("a")
        cache["a"] = s
        assert cache["a"] is s
        assert "a" in cache
        assert len(cache) == 1

    def test_get_default(self, cache):
        assert cache.get("missing") is None
        assert cache.get("missing", 42) == 42

    def test_pop_does_not_trigger_save(self, cache, make_session, saved_keys):
        cache["a"] = make_session("a")
        result = cache.pop("a")
        assert result.key == "a"
        assert "a" not in cache
        assert saved_keys == []

    def test_pop_missing_default(self, cache):
        assert cache.pop("missing", None) is None
        with pytest.raises(KeyError):
            cache.pop("missing")

    def test_items_iteration(self, cache, make_session):
        cache["a"] = make_session("a")
        cache["b"] = make_session("b")
        keys = [k for k, _ in cache.items()]
        assert set(keys) == {"a", "b"}

    def test_maxsize_eviction_saves_before_evict(self, cache, make_session, saved_keys):
        cache["a"] = make_session("a")
        cache["b"] = make_session("b")
        cache["c"] = make_session("c")
        assert len(cache) == 3
        assert saved_keys == []

        cache["d"] = make_session("d")
        assert len(cache) == 3
        assert len(saved_keys) == 1
        assert saved_keys[0] == "a"
        assert "a" not in cache
        assert "d" in cache

    def test_idle_eviction(self, cache, make_session, saved_keys):
        cache["a"] = make_session("a")
        cache["b"] = make_session("b")
        time.sleep(0.6)
        evicted = cache.evict_idle()
        assert evicted == 2
        assert len(cache) == 0
        assert set(saved_keys) == {"a", "b"}

    def test_active_session_not_evicted_by_idle(self, cache, make_session, saved_keys):
        cache["a"] = make_session("a")
        time.sleep(0.3)
        _ = cache["a"]
        time.sleep(0.3)
        evicted = cache.evict_idle()
        assert evicted == 0
        assert "a" in cache

    def test_reentrancy_guard_on_save(self, make_session):
        """save() writes back to _cache[key] = session; evict must not recurse."""
        reentrancy_log = []

        def save_fn(session):
            reentrancy_log.append(f"save:{session.key}")
            evicting_cache[session.key] = session

        evicting_cache = EvictingSessionCache(save_fn, maxsize=2, idle_timeout=0.1)
        evicting_cache["a"] = make_session("a")
        evicting_cache["b"] = make_session("b")
        time.sleep(0.2)

        evicted = evicting_cache.evict_idle()
        assert evicted == 2
        assert len(evicting_cache) == 0
        assert "save:a" in reentrancy_log
        assert "save:b" in reentrancy_log

    def test_flush_all_sees_all_sessions(self, cache, make_session):
        cache["a"] = make_session("a")
        cache["b"] = make_session("b")
        cache["c"] = make_session("c")
        items = list(cache.items())
        assert len(items) == 3

    def test_len_and_bool(self, cache, make_session):
        assert len(cache) == 0
        assert not cache
        cache["a"] = make_session("a")
        assert len(cache) == 1
        assert cache

    def test_lru_eviction_order(self, cache, make_session, saved_keys):
        """Most recently accessed key survives eviction."""
        cache["a"] = make_session("a")
        cache["b"] = make_session("b")
        cache["c"] = make_session("c")
        _ = cache["a"]
        cache["d"] = make_session("d")
        assert saved_keys[0] == "b"
        assert "a" in cache
        assert "b" not in cache
