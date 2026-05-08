"""Config file reading, writing, and masking."""

from __future__ import annotations

import json
import hashlib
import tomllib
from pathlib import Path
from typing import Any

from ava.console.security import mask_config, reveal_field


EDITABLE_CONFIGS = {
    "config.json": "config.json",
    "nanobot-config.json": "config.json",
    "console-config.json": "console/console-config.json",
    "codex-config.toml": "console/agents/codex/config.toml",
    "claude-code-settings.json": "console/agents/claude_code/settings.json",
    "image-gen-config.json": "console/agents/image_gen/config.json",
    "extra_config.json": "extra_config.json",
    "cron/jobs.json": "cron/jobs.json",
}

CONFIG_TEMPLATES = {
    "codex-config.toml": '# AVA-managed Codex config\nmodel = ""\napi_base = ""\n',
    "claude-code-settings.json": json.dumps({
        "model": "claude-sonnet-4-20250514",
        "maxTurns": 15,
        "allowedTools": "Read,Edit,Bash,Glob,Grep",
    }, indent=2),
    "image-gen-config.json": json.dumps({
        "model": "",
        "provider": "",
        "timeout": 300,
        "background": True,
    }, indent=2),
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
        if name == "console-config.json" and not full.exists():
            return self._read_console_config_projection(mask=mask)
        if name in CONFIG_TEMPLATES and not full.exists():
            return {
                "content": CONFIG_TEMPLATES[name],
                "mtime": 0,
                "format": self._format_for_name(name),
            }
        if not full.exists():
            raise FileNotFoundError(f"Config file not found: {full}")

        content = full.read_text("utf-8")
        mtime = full.stat().st_mtime

        if name.endswith(".toml"):
            return {"content": content, "mtime": mtime, "format": "toml"}
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

    def _read_console_config_projection(self, mask: bool = True) -> dict:
        legacy = self._dir / "config.json"
        if not legacy.exists():
            raise FileNotFoundError(f"Config file not found: {self._dir / EDITABLE_CONFIGS['console-config.json']}")

        parsed = json.loads(legacy.read_text("utf-8"))
        gateway = parsed.get("gateway", {}) if isinstance(parsed, dict) else {}
        projected = {"gateway": gateway}
        if mask:
            projected = mask_config(projected)
        return {
            "content": json.dumps(projected, indent=2, ensure_ascii=False),
            "mtime": 0,
            "format": "json",
        }

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

        self._parse_config_content(name, content)

        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, "utf-8")
        return {"mtime": full.stat().st_mtime}

    def read_config_revision(self, name: str) -> dict[str, Any]:
        if name not in EDITABLE_CONFIGS:
            raise ValueError(f"Config '{name}' not found")
        full = self._dir / EDITABLE_CONFIGS[name]
        content = full.read_text("utf-8") if full.exists() else ""
        metadata = self._read_revision_metadata(name)
        revision = self._revision_for_content(content)
        return {
            "content": content,
            "revision": revision,
            "etag": revision,
            "last_modified_by": metadata.get("last_modified_by", ""),
        }

    def update_config_with_revision(
        self,
        name: str,
        content: str,
        *,
        expected_revision: str,
        user_id: str,
    ) -> dict[str, Any]:
        current = self.read_config_revision(name)
        if expected_revision != current["revision"]:
            raise ValueError("conflict: revision mismatch")
        self._parse_config_content(name, content)
        full = self._dir / EDITABLE_CONFIGS[name]
        full.parent.mkdir(parents=True, exist_ok=True)
        full.write_text(content, "utf-8")
        revision = self._revision_for_content(content)
        self._write_revision_metadata(name, {"revision": revision, "etag": revision, "last_modified_by": user_id})
        return {"revision": revision, "etag": revision, "last_modified_by": user_id}

    def _revision_metadata_path(self, name: str) -> Path:
        rel = EDITABLE_CONFIGS[name].replace("/", "__")
        return self._dir / "console" / "config-revisions" / f"{rel}.json"

    def _read_revision_metadata(self, name: str) -> dict[str, Any]:
        path = self._revision_metadata_path(name)
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text("utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_revision_metadata(self, name: str, metadata: dict[str, Any]) -> None:
        path = self._revision_metadata_path(name)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(json.dumps(metadata, indent=2, ensure_ascii=False), encoding="utf-8")

    @staticmethod
    def _revision_for_content(content: str) -> str:
        return hashlib.sha256(content.encode("utf-8")).hexdigest()

    def _parse_config_content(self, name: str, content: str) -> Any:
        if name.endswith(".json") and not name.endswith(".jsonc"):
            try:
                return json.loads(content)
            except json.JSONDecodeError as exc:
                raise ValueError(f"Invalid JSON: {exc.msg}") from exc
        if name.endswith(".toml"):
            try:
                return tomllib.loads(content)
            except tomllib.TOMLDecodeError as exc:
                raise ValueError(f"Invalid TOML: {exc}") from exc
        return content

    def _format_for_name(self, name: str) -> str:
        if name.endswith(".toml"):
            return "toml"
        if name.endswith(".jsonc"):
            return "jsonc"
        if name.endswith(".json"):
            return "json"
        return "text"

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
