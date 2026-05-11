"""cloudflared quick tunnel lifecycle for LAN Access."""

from __future__ import annotations

import os
import platform
import queue
import re
import subprocess
import threading
import time
from dataclasses import dataclass
from pathlib import Path


TRYCLOUDFLARE_RE = re.compile(r"https://[a-zA-Z0-9-]+\.trycloudflare\.com")


@dataclass
class TunnelStatus:
    running: bool
    public_url: str
    binary_path: str
    pid: int | None = None
    error: str = ""


class TunnelService:
    def __init__(self, *, repo_root: Path, console_port: int):
        self._repo_root = repo_root
        self._console_port = console_port
        self._process: subprocess.Popen | None = None
        self._public_url = ""
        self._error = ""

    @property
    def running(self) -> bool:
        return self._process is not None and self._process.poll() is None

    @property
    def public_url(self) -> str:
        return self._public_url if self.running else ""

    def start(self) -> TunnelStatus:
        if self.running:
            return self.status()
        binary = self.binary_path()
        if not binary.exists():
            self._error = f"cloudflared binary not found: {binary}"
            return self.status()

        output_queue: queue.Queue[str] = queue.Queue()
        self._process = subprocess.Popen(
            [str(binary), "tunnel", "--url", f"http://127.0.0.1:{self._console_port}"],
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )
        for stream in (self._process.stdout, self._process.stderr):
            if stream is not None:
                threading.Thread(
                    target=_read_stream,
                    args=(stream, output_queue),
                    daemon=True,
                ).start()

        deadline = time.monotonic() + 5
        while time.monotonic() < deadline:
            if not self.running:
                self._error = "cloudflared exited before public URL was available"
                return self.status()
            try:
                line = output_queue.get(timeout=0.1)
            except queue.Empty:
                continue
            match = TRYCLOUDFLARE_RE.search(line)
            if match:
                self._public_url = match.group(0)
                self._error = ""
                return self.status()
        self._error = "cloudflared did not report a public URL"
        return self.status()

    def stop(self) -> TunnelStatus:
        process = self._process
        if process is not None and process.poll() is None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
        self._process = None
        self._public_url = ""
        self._error = ""
        return self.status()

    def status(self) -> TunnelStatus:
        process = self._process if self.running else None
        return TunnelStatus(
            running=process is not None,
            public_url=self.public_url,
            binary_path=str(self.binary_path()),
            pid=process.pid if process is not None else None,
            error=self._error,
        )

    def binary_path(self) -> Path:
        system = platform.system().lower()
        machine = platform.machine().lower()
        if system == "darwin":
            os_name = "darwin"
        elif system == "windows":
            os_name = "windows"
        else:
            os_name = "linux"
        arch = "arm64" if machine in {"arm64", "aarch64"} else "amd64"
        name = "cloudflared.exe" if os_name == "windows" else "cloudflared"
        return self._repo_root / "vendor" / "cloudflared" / f"{os_name}-{arch}" / name


def _read_stream(stream, output_queue: queue.Queue[str]) -> None:
    for line in stream:
        output_queue.put(line)
