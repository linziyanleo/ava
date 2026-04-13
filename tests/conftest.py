"""Shared pytest bootstrap for the extracted Ava repo."""

from __future__ import annotations

import os

from ava.adapters.nanobot.discovery import ensure_nanobot_on_sys_path, resolve_nanobot_root


try:
    root = resolve_nanobot_root()
except RuntimeError:
    root = None
else:
    os.environ.setdefault("AVA_NANOBOT_ROOT", str(root))
    ensure_nanobot_on_sys_path(explicit_root=root)
