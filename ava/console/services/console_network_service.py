"""Runtime console bind/SSL reload coordination."""

from __future__ import annotations

import os
from dataclasses import dataclass
from pathlib import Path
from typing import Callable


ReloadCallback = Callable[[], dict]


@dataclass
class ConsoleNetworkStatus:
    host: str
    port: int
    ssl_certfile: str | None
    ssl_keyfile: str | None
    pid: int


class ConsoleNetworkService:
    def __init__(
        self,
        *,
        nanobot_dir: Path,
        port: int,
        lan_access,
        lan_https,
        tunnel,
    ):
        self._nanobot_dir = nanobot_dir
        self._port = port
        self._lan_access = lan_access
        self._lan_https = lan_https
        self._tunnel = tunnel
        self._reload_callback: ReloadCallback | None = None

    def set_reload_callback(self, callback: ReloadCallback | None) -> None:
        self._reload_callback = callback

    @property
    def port(self) -> int:
        return self._port

    def current_host(self) -> str:
        state = self._lan_access.read_state()
        return "0.0.0.0" if state.get("enabled") else "127.0.0.1"

    def ssl_paths(self) -> tuple[str | None, str | None]:
        cert, key = self._lan_https.ssl_paths()
        return cert, key

    def status(self) -> ConsoleNetworkStatus:
        cert, key = self.ssl_paths()
        return ConsoleNetworkStatus(
            host=self.current_host(),
            port=self._port,
            ssl_certfile=cert,
            ssl_keyfile=key,
            pid=os.getpid(),
        )

    def reload(self) -> dict:
        if self._reload_callback is None:
            return {"reloaded": False, "fallback": "no_callback", "pid": os.getpid()}
        return self._reload_callback()
