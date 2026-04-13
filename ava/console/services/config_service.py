"""Config file reading, writing, and masking."""

from __future__ import annotations

import json
import os
from pathlib import Path

from ava.console.security import mask_config, reveal_field


EDITABLE_CONFIGS = {
    "config.json": "config.json",
    "extra_config.json": "extra_config.json",
    "cron/jobs.json": "cron/jobs.json",
}


class ConfigService:
    def __init__(self, nanobot_dir: Path):
        self._dir = nanobot_dir

    def list_configs(self) -> list[dict]:
        result = []
        for label, rel_path in EDITABLE_CONFIGS.items():
            full = self._dir / rel_path
            result.append({
                "name": label,
                "path": rel_path,
                "exists": full.exists(),
                "size": full.stat().st_size if full.exists() else 0,
            })
        return result

    def read_config(self, name: str, mask: bool = True) -> dict:
        if name not in EDITABLE_CONFIGS:
            raise ValueError(f"Config '{name}' not found")
        full = self._dir / EDITABLE_CONFIGS[name]
        if not full.exists():
            raise FileNotFoundError(f"Config file not found: {full}")

        content = full.read_text("utf-8")
        mtime = full.stat().st_mtime

        if name.endswith(".jsonc"):
            return {"content": content, "mtime": mtime, "format": "jsonc"}

        try:
            parsed = json.loads(content)
            if mask:
                parsed = mask_config(parsed)
            return {
                "content": json.dumps(parsed, indent=2, ensure_ascii=False),
                "mtime": mtime,
                "format": "json",
            }
        except json.JSONDecodeError:
            return {"content": content, "mtime": mtime, "format": "text"}

    def update_config(self, name: str, content: str, expected_mtime: float) -> dict:
        if name not in EDITABLE_CONFIGS:
            raise ValueError(f"Config '{name}' not found")
        full = self._dir / EDITABLE_CONFIGS[name]

        if full.exists():
            current_mtime = full.stat().st_mtime
            if abs(current_mtime - expected_mtime) > 0.01:
                raise ValueError(
                    "File was modified by another process. "
                    "Please reload and try again."
                )

        if name.endswith(".json") and not name.endswith(".jsonc"):
            json.loads(content)

        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, "utf-8")
        return {"mtime": full.stat().st_mtime}

    def reveal_secret(self, name: str, field_path: str) -> str | None:
        if name not in EDITABLE_CONFIGS:
            raise ValueError(f"Config '{name}' not found")
        full = self._dir / EDITABLE_CONFIGS[name]
        if not full.exists():
            return None
        try:
            config = json.loads(full.read_text("utf-8"))
        except json.JSONDecodeError:
            return None
        return reveal_field(config, field_path)
