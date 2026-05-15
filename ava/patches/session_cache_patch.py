"""Patch SessionManager._cache with an evicting variant that saves before evict."""

from __future__ import annotations

import time
from collections.abc import Iterator, ItemsView
from typing import Any, Callable, TYPE_CHECKING

from loguru import logger

from ava.launcher import register_patch

if TYPE_CHECKING:
    pass


class EvictingSessionCache:
    """Dict-like wrapper with idle TTL + maxsize + save-before-evict.

    Reentrancy guard: evict calls save, which may write back via
    ``_cache[session.key] = session``.  ``_evicting`` tracks keys
    being evicted so ``__setitem__`` skips access-time updates and
    capacity checks for those keys, and evict finishes by popping them.
    """

    def __init__(
        self,
        save_fn: Callable[[Any], None],
        *,
        maxsize: int = 200,
        idle_timeout: float = 7200.0,
    ) -> None:
        self._save_fn = save_fn
        self._maxsize = maxsize
        self._idle_timeout = idle_timeout
        self._data: dict[str, Any] = {}
        self._access: dict[str, float] = {}
        self._evicting: set[str] = set()
        self._last_idle_check: float = time.monotonic()
        self._idle_check_interval: float = 300.0

    def __setitem__(self, key: str, value: Any) -> None:
        if key in self._evicting:
            self._data[key] = value
            return
        self._data[key] = value
        self._access[key] = time.monotonic()
        self._maybe_evict_idle()
        if len(self._data) > self._maxsize:
            self._evict_lru()

    def __getitem__(self, key: str) -> Any:
        value = self._data[key]
        self._access[key] = time.monotonic()
        self._maybe_evict_idle()
        return value

    def __contains__(self, key: object) -> bool:
        present = key in self._data
        if present and isinstance(key, str):
            self._access[key] = time.monotonic()
        return present

    def __len__(self) -> int:
        return len(self._data)

    def __bool__(self) -> bool:
        return bool(self._data)

    def __iter__(self) -> Iterator[str]:
        return iter(self._data)

    def get(self, key: str, default: Any = None) -> Any:
        try:
            return self[key]
        except KeyError:
            return default

    def pop(self, key: str, *args: Any) -> Any:
        self._access.pop(key, None)
        return self._data.pop(key, *args)

    def items(self) -> ItemsView[str, Any]:
        return self._data.items()

    def keys(self):
        return self._data.keys()

    def values(self):
        return self._data.values()

    def _maybe_evict_idle(self) -> None:
        now = time.monotonic()
        if (now - self._last_idle_check) < self._idle_check_interval:
            return
        self._last_idle_check = now
        self.evict_idle()

    def evict_idle(self) -> int:
        now = time.monotonic()
        idle_keys = [
            k for k, t in self._access.items()
            if (now - t) >= self._idle_timeout
        ]
        evicted = 0
        for key in idle_keys:
            if self._safe_evict(key):
                evicted += 1
        return evicted

    def _evict_lru(self) -> None:
        if not self._access:
            return
        candidates = sorted(self._access, key=self._access.get)  # type: ignore[arg-type]
        for key in candidates:
            if self._safe_evict(key):
                return

    def _safe_evict(self, key: str) -> bool:
        """Evict a session after saving it. Returns False if save failed (entry kept)."""
        session = self._data.get(key)
        if session is None:
            self._access.pop(key, None)
            return True
        self._evicting.add(key)
        try:
            self._save_fn(session)
        except Exception:
            logger.warning("Failed to save session {} before eviction; keeping in cache", key)
            self._evicting.discard(key)
            return False
        finally:
            self._evicting.discard(key)
        self._data.pop(key, None)
        self._access.pop(key, None)
        return True


def apply_session_cache_patch() -> str:
    from nanobot.session.manager import SessionManager

    if getattr(SessionManager.__init__, "_ava_session_cache_patched", False):
        return "SessionManager._cache patch already applied (skipped)"

    orig_init = SessionManager.__init__

    def patched_init(self, workspace, *args, **kwargs):
        orig_init(self, workspace, *args, **kwargs)
        self._cache = EvictingSessionCache(
            save_fn=self.save,
            maxsize=200,
            idle_timeout=7200.0,
        )

    patched_init._ava_session_cache_patched = True
    SessionManager.__init__ = patched_init
    return "SessionManager._cache replaced with EvictingSessionCache (maxsize=200, idle=2h)"


register_patch("session_cache", apply_session_cache_patch)
