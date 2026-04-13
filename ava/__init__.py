"""
ava — Sidecar extension package for nanobot.

This package contains all custom extensions, tools, and patches
that are applied at runtime via Monkey Patching, keeping the
upstream nanobot source 100% pristine.

Directory layout:
    ava/
    ├── __init__.py          # This file
    ├── launcher.py          # Entry point: applies all patches before nanobot starts
    ├── patches/             # Monkey patch modules (one per concern)
    │   ├── __init__.py
    │   ├── tools_patch.py   # Injects custom tools into AgentLoop
    │   ├── console_patch.py # Mounts Console Web UI onto gateway
    │   ├── storage_patch.py # Swaps JSONL storage for SQLite
    │   └── channel_patch.py # Injects message batcher, backfill, etc.
    ├── tools/               # Custom Tool implementations
    ├── console/             # Web Console (FastAPI app, routes, services)
    ├── storage/             # SQLite storage layer
    ├── channels/            # Channel extensions (batcher, etc.)
    ├── session/             # Session extensions (backfill, etc.)
    ├── skills/              # Custom skill definitions
    └── templates/           # Template overrides
"""

__version__ = "0.1.0"
