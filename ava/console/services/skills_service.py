"""Skills and tools management service.

Manages three skill sources:
  1. ava/skills/   — sidecar custom skills (install target)
  2. .agents/      — external agent skills (read-only discovery)
  3. nanobot/skills/ — upstream builtin (read-only)

Enabled/disabled state is persisted in SQLite ``skill_config`` table.
"""

from __future__ import annotations

import asyncio
import json
import os
import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from ava.storage.database import Database


class MCPStatusInspector:
    """Read-only MCP status and short-lived probe helper."""

    def __init__(self, nanobot_dir: Path, agent_loop: Any | None = None):
        self.nanobot_dir = nanobot_dir
        self.agent_loop = agent_loop

    def list_mcp_servers(self) -> dict[str, Any]:
        servers = self._read_configured_servers()
        runtime = self._runtime_summary()
        return {
            "servers": [
                self._server_status(name, cfg)
                for name, cfg in sorted(servers.items())
            ],
            "runtime": runtime,
        }

    async def probe_mcp_server(self, name: str, timeout: float = 3.0) -> dict[str, Any]:
        servers = self._read_configured_servers()
        if name not in servers:
            raise ValueError(f"MCP server '{name}' is not configured")

        cfg = self._normalize_server_config(servers[name])
        try:
            raw_tools = await asyncio.wait_for(
                self._probe_server(name, cfg),
                timeout=timeout,
            )
        except asyncio.TimeoutError:
            return {
                "ok": False,
                "name": name,
                "status": "timeout",
                "raw_tools": [],
                "wrapped_tools": [],
                "error": f"Probe timed out after {timeout:g}s",
            }
        except Exception as exc:
            return {
                "ok": False,
                "name": name,
                "status": "failed",
                "raw_tools": [],
                "wrapped_tools": [],
                "error": f"{type(exc).__name__}: {exc}",
            }

        return {
            "ok": True,
            "name": name,
            "status": "connected",
            "raw_tools": raw_tools,
            "wrapped_tools": [f"mcp_{name}_{tool}" for tool in raw_tools],
            "error": None,
        }

    def reconnect_all(self) -> dict[str, Any]:
        return {
            "ok": False,
            "status": "unsupported",
            "scope": "all",
            "detail": (
                "Runtime MCP hot reconnect is not supported safely yet; "
                "restart the gateway after MCP config edits."
            ),
        }

    def _config_path(self) -> Path:
        return self.nanobot_dir / "config.json"

    def _read_configured_servers(self) -> dict[str, Any]:
        path = self._config_path()
        if not path.exists():
            return {}
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception as exc:
            logger.warning("Failed to read MCP config from {}: {}", path, exc)
            return {}
        tools = payload.get("tools")
        if not isinstance(tools, dict):
            return {}
        servers = tools.get("mcpServers")
        if servers is None:
            servers = tools.get("mcp_servers")
        return servers if isinstance(servers, dict) else {}

    @staticmethod
    def _normalize_server_config(cfg: Any) -> dict[str, Any]:
        cfg = cfg if isinstance(cfg, dict) else {}
        return {
            "type": cfg.get("type") or "",
            "command": cfg.get("command") or "",
            "args": list(cfg.get("args") or []),
            "env": dict(cfg.get("env") or {}),
            "url": cfg.get("url") or "",
            "headers": dict(cfg.get("headers") or {}),
            "toolTimeout": cfg.get("toolTimeout", cfg.get("tool_timeout", 30)),
            "enabledTools": list(cfg.get("enabledTools", cfg.get("enabled_tools", [])) or []),
        }

    @staticmethod
    def _redact_mcp_config(cfg: dict[str, Any]) -> dict[str, Any]:
        redacted = dict(cfg)
        redacted["env"] = {key: "****" for key in sorted((cfg.get("env") or {}).keys())}
        redacted["headers"] = {key: "****" for key in sorted((cfg.get("headers") or {}).keys())}
        return redacted

    def _server_status(self, name: str, raw_cfg: Any) -> dict[str, Any]:
        cfg = self._normalize_server_config(raw_cfg)
        registered_tools = self._registered_tools_for(name)
        connected_servers = set(self._connected_server_names())
        agent_loaded = self.agent_loop is not None
        mcp_connected = bool(getattr(self.agent_loop, "_mcp_connected", False)) if agent_loaded else False
        mcp_connecting = bool(getattr(self.agent_loop, "_mcp_connecting", False)) if agent_loaded else False

        if not agent_loaded:
            status = "unloaded"
        elif mcp_connecting:
            status = "connecting"
        elif name in connected_servers or registered_tools:
            status = "connected"
        elif mcp_connected:
            status = "failed"
        else:
            status = "configured"

        return {
            "name": name,
            "status": status,
            "config_redacted": self._redact_mcp_config(cfg),
            "redacted": ["env", "headers"],
            "registered_tools": registered_tools,
            "last_error": None,
            "last_connected_at": None,
        }

    def _runtime_summary(self) -> dict[str, Any]:
        if self.agent_loop is None:
            return {
                "loaded": False,
                "mcp_connected": False,
                "mcp_connecting": False,
                "connected_servers": [],
            }
        return {
            "loaded": True,
            "mcp_connected": bool(getattr(self.agent_loop, "_mcp_connected", False)),
            "mcp_connecting": bool(getattr(self.agent_loop, "_mcp_connecting", False)),
            "connected_servers": self._connected_server_names(),
        }

    def _connected_server_names(self) -> list[str]:
        stacks = getattr(self.agent_loop, "_mcp_stacks", None)
        if isinstance(stacks, dict):
            return sorted(str(name) for name in stacks.keys())
        return []

    def _registered_tools_for(self, server_name: str) -> list[str]:
        prefix = f"mcp_{server_name}_"
        tools = getattr(self.agent_loop, "tools", None)
        names: list[str] = []
        if tools and hasattr(tools, "get_definitions"):
            for schema in tools.get_definitions():
                name = self._schema_name(schema)
                if name.startswith(prefix):
                    names.append(name)
        if not names and tools and hasattr(tools, "tool_names"):
            names = [name for name in tools.tool_names if str(name).startswith(prefix)]
        return sorted(set(names))

    @staticmethod
    def _schema_name(schema: dict[str, Any]) -> str:
        fn = schema.get("function")
        if isinstance(fn, dict) and isinstance(fn.get("name"), str):
            return fn["name"]
        name = schema.get("name")
        return name if isinstance(name, str) else ""

    async def _probe_server(self, name: str, cfg: dict[str, Any]) -> list[str]:
        transport_type = cfg.get("type") or ("stdio" if cfg.get("command") else "")
        if transport_type != "stdio":
            raise RuntimeError(f"MCP probe only supports stdio servers today, got {transport_type or 'unknown'}")
        return await self._probe_stdio_server(name, cfg)

    async def _probe_stdio_server(self, name: str, cfg: dict[str, Any]) -> list[str]:
        from mcp import ClientSession, StdioServerParameters
        from mcp.client.stdio import stdio_client

        command = str(cfg.get("command") or "")
        if not command:
            raise RuntimeError("stdio MCP server has no command")
        params = StdioServerParameters(
            command=command,
            args=[str(arg) for arg in cfg.get("args") or []],
            env={**os.environ, **(cfg.get("env") or {})},
        )
        async with stdio_client(params) as (read, write):
            async with ClientSession(read, write) as session:
                await session.initialize()
                tools = await session.list_tools()
        return [str(tool.name) for tool in tools.tools]


class SkillsService:
    """Service for managing skills and tools."""

    def __init__(
        self,
        workspace: Path,
        builtin_skills_dir: Path,
        nanobot_dir: Path,
        upstream_skills_dir: Path | None = None,
        db: Database | None = None,
    ):
        self.workspace = workspace
        self.builtin_skills_dir = builtin_skills_dir  # ava/skills/
        self.nanobot_dir = nanobot_dir
        self.nanobot_skills_dir = upstream_skills_dir
        self.agents_dir = Path.home() / ".agents" / "skills"
        self.tools_dir = Path(__file__).parent.parent.parent / "tools"
        self.db = db

    # ─── Tools ──────────────────────────────────────────────────────────────────

    def list_tools(self) -> list[dict[str, Any]]:
        """List all built-in tools with their metadata."""
        tools = []

        tool_files = [
            f for f in self.tools_dir.glob("*.py")
            if f.name not in ("__init__.py", "base.py", "registry.py")
        ]

        for tool_file in sorted(tool_files):
            tool_info = self._extract_tool_info(tool_file)
            if tool_info:
                tools.extend(tool_info)

        return tools

    def mcp_status(self, agent_loop: Any | None = None) -> dict[str, Any]:
        return MCPStatusInspector(self.nanobot_dir, agent_loop=agent_loop).list_mcp_servers()

    async def test_mcp_server(self, name: str) -> dict[str, Any]:
        return await MCPStatusInspector(self.nanobot_dir).probe_mcp_server(name)

    def reconnect_mcp(self, agent_loop: Any | None = None) -> dict[str, Any]:
        return MCPStatusInspector(self.nanobot_dir, agent_loop=agent_loop).reconnect_all()

    def _extract_tool_info(self, tool_file: Path) -> list[dict[str, Any]]:
        """Extract tool information from a tool file."""
        tools = []
        content = tool_file.read_text(encoding="utf-8")

        class_pattern = re.compile(
            r'class\s+(\w+)\(Tool\):\s*"""([^"]+)"""',
            re.MULTILINE,
        )

        for match in class_pattern.finditer(content):
            class_name = match.group(1)
            description = match.group(2).strip()

            name = self._extract_property_value(content, class_name, "name")
            if not name:
                name = re.sub(r"Tool$", "", class_name)
                name = re.sub(r"(?<!^)(?=[A-Z])", "_", name).lower()

            tools.append({
                "name": name,
                "class": class_name,
                "description": description,
                "file": tool_file.name,
            })

        return tools

    def _extract_property_value(self, content: str, class_name: str, prop_name: str) -> str | None:
        """Extract a property value from class definition."""
        pattern = rf"class\s+{class_name}.*?(?=class\s+\w+|$)"
        class_match = re.search(pattern, content, re.DOTALL)
        if class_match:
            class_content = class_match.group(0)
            prop_pattern = rf'{prop_name}\s*=\s*["\']([^"\']+)["\']'
            prop_match = re.search(prop_pattern, class_content)
            if prop_match:
                return prop_match.group(1)
        return None

    # ─── Skills — listing ────────────────────────────────────────────────────────

    def _now_iso(self) -> str:
        return datetime.now(timezone.utc).isoformat()

    def _enabled_map(self) -> dict[str, bool]:
        """Return {name: enabled} from SQLite."""
        if not self.db:
            return {}
        try:
            rows = self.db.fetchall("SELECT name, enabled FROM skill_config")
            return {r["name"]: bool(r["enabled"]) for r in rows}
        except Exception:
            return {}

    def _config_row(self, name: str) -> dict | None:
        if not self.db:
            return None
        try:
            row = self.db.fetchone("SELECT * FROM skill_config WHERE name = ?", (name,))
            return dict(row) if row else None
        except Exception:
            return None

    def list_skills(self) -> list[dict[str, Any]]:
        """List all skills from three sources with enabled state."""
        skills: list[dict[str, Any]] = []
        seen: set[str] = set()
        enabled_map = self._enabled_map()

        # 1. ava/skills/ (sidecar custom — highest priority)
        self._scan_dir(self.builtin_skills_dir, "ava", skills, seen, enabled_map)

        # 2. .agents/ (external agent skills)
        self._scan_dir(self.agents_dir, "agents", skills, seen, enabled_map, follow_symlinks=True)

        # 3. nanobot/skills/ (upstream builtin)
        self._scan_dir(self.nanobot_skills_dir, "builtin", skills, seen, enabled_map)

        return skills

    def _scan_dir(
        self,
        base: Path,
        source: str,
        skills: list[dict],
        seen: set[str],
        enabled_map: dict[str, bool],
        follow_symlinks: bool = False,
    ) -> None:
        if not base or not base.exists():
            return
        for entry in sorted(base.iterdir()):
            resolved = entry.resolve() if (follow_symlinks and entry.is_symlink()) else entry
            if not resolved.is_dir() or entry.name in seen or entry.name == "__pycache__":
                continue
            skill_file = resolved / "SKILL.md"
            if not skill_file.exists():
                continue
            meta = self._parse_skill_metadata(skill_file)
            enabled = enabled_map.get(entry.name, True)
            cfg = self._config_row(entry.name)
            skills.append({
                "name": entry.name,
                "source": source,
                "path": str(skill_file),
                "enabled": enabled,
                "install_method": cfg["install_method"] if cfg else None,
                "git_url": cfg["git_url"] if cfg else None,
                **meta,
            })
            seen.add(entry.name)

    def _parse_skill_metadata(self, skill_file: Path) -> dict[str, Any]:
        """Parse skill metadata from SKILL.md frontmatter."""
        content = skill_file.read_text(encoding="utf-8")
        meta: dict[str, Any] = {"description": "", "always": False}

        if content.startswith("---"):
            match = re.match(r"^---\n(.*?)\n---", content, re.DOTALL)
            if match:
                for line in match.group(1).split("\n"):
                    if ":" in line:
                        key, value = line.split(":", 1)
                        key = key.strip()
                        value = value.strip().strip("\"'")
                        if key == "description":
                            meta["description"] = value
                        elif key == "always":
                            meta["always"] = value.lower() == "true"

        return meta

    def get_skill(self, name: str) -> dict[str, Any] | None:
        """Get a single skill by name."""
        for skill in self.list_skills():
            if skill["name"] == name:
                return skill
        return None

    # ─── Skills — toggle ─────────────────────────────────────────────────────────

    def toggle_skill(self, name: str, enabled: bool) -> dict[str, Any]:
        """Enable or disable a skill (any source). Persists to SQLite."""
        if not self.db:
            raise RuntimeError("Database not available")

        now = self._now_iso()
        self.db.execute(
            """INSERT INTO skill_config (name, source, enabled, updated_at)
               VALUES (?, '', ?, ?)
               ON CONFLICT(name) DO UPDATE SET enabled = ?, updated_at = ?""",
            (name, int(enabled), now, int(enabled), now),
        )
        self.db.commit()
        return {"ok": True, "name": name, "enabled": enabled}

    # ─── Skills — install ────────────────────────────────────────────────────────

    def install_skill_from_git(self, git_url: str, name: str | None = None) -> dict[str, Any]:
        """Install a skill from a GitHub URL into ~/.agents/skills/.

        Supports GitHub repo URLs, tree URLs (subdirectory), and blob URLs.
        Uses `gh` CLI to download only the needed files without full clone.
        """
        from ava.console.services.gh_skill_installer import download_skill_from_github

        self.agents_dir.mkdir(parents=True, exist_ok=True)
        result = download_skill_from_github(git_url, name=name, target_dir=self.agents_dir)
        self._record_install(result["name"], "agents", "git", git_url=git_url)
        return result

    def install_skill_from_path(self, source_path: str, name: str | None = None) -> dict[str, Any]:
        """Install a skill by copying from a local path into ~/.agents/skills/."""
        source = Path(source_path).expanduser().resolve()

        if not source.exists():
            raise FileNotFoundError(f"Source path does not exist: {source}")
        if not source.is_dir():
            raise ValueError(f"Source must be a directory: {source}")

        skill_file = source / "SKILL.md"
        if not skill_file.exists():
            raise ValueError(f"No SKILL.md found in {source}")

        if not name:
            name = source.name

        self.agents_dir.mkdir(parents=True, exist_ok=True)
        target_dir = self.agents_dir / name

        if target_dir.exists():
            raise ValueError(f"Skill '{name}' already exists")

        shutil.copytree(source, target_dir)
        self._record_install(name, "agents", "path")
        return {"ok": True, "name": name, "path": str(target_dir)}

    def install_skill_from_upload(self, name: str, files: dict[str, bytes]) -> dict[str, Any]:
        """Install a skill from uploaded files (native file picker).

        Args:
            name: skill directory name
            files: mapping of relative_path → content bytes
        """
        self.agents_dir.mkdir(parents=True, exist_ok=True)
        target_dir = self.agents_dir / name

        if target_dir.exists():
            raise ValueError(f"Skill '{name}' already exists")

        has_skill_md = False
        try:
            for rel_path, content in files.items():
                # Sanitize: strip leading skill-name/ prefix if browser includes it
                clean = rel_path.lstrip("/")
                parts = Path(clean).parts
                # If first part matches the skill name, strip it
                if len(parts) > 1 and parts[0] == name:
                    clean = str(Path(*parts[1:]))
                dest = target_dir / clean
                dest.parent.mkdir(parents=True, exist_ok=True)
                dest.write_bytes(content)
                if dest.name == "SKILL.md":
                    has_skill_md = True

            if not has_skill_md:
                shutil.rmtree(target_dir, ignore_errors=True)
                raise ValueError("No SKILL.md found in uploaded files")

            self._record_install(name, "agents", "upload")
            return {"ok": True, "name": name, "path": str(target_dir)}
        except Exception:
            if target_dir.exists():
                shutil.rmtree(target_dir, ignore_errors=True)
            raise

    def _record_install(self, name: str, source: str, method: str, git_url: str | None = None) -> None:
        if not self.db:
            return
        now = self._now_iso()
        try:
            self.db.execute(
                """INSERT INTO skill_config (name, source, enabled, installed_at, install_method, git_url, updated_at)
                   VALUES (?, ?, 1, ?, ?, ?, ?)
                   ON CONFLICT(name) DO UPDATE SET
                     source = ?, enabled = 1, installed_at = ?, install_method = ?, git_url = ?, updated_at = ?""",
                (name, source, now, method, git_url, now,
                 source, now, method, git_url, now),
            )
            self.db.commit()
        except Exception as e:
            logger.warning("Failed to record skill install: {}", e)

    # ─── Skills — delete ─────────────────────────────────────────────────────────

    def delete_skill(self, name: str) -> dict[str, Any]:
        """Delete an ava/skills/ skill."""
        skill_dir = self.builtin_skills_dir / name

        if not skill_dir.exists():
            raise FileNotFoundError(f"Skill '{name}' not found")

        # Only allow deleting ava/skills/ skills
        if not str(skill_dir.resolve()).startswith(str(self.builtin_skills_dir.resolve())):
            raise PermissionError("Cannot delete built-in skills")

        shutil.rmtree(skill_dir)

        # Remove config record
        if self.db:
            try:
                self.db.execute("DELETE FROM skill_config WHERE name = ?", (name,))
                self.db.commit()
            except Exception as e:
                logger.warning("Failed to remove skill config: {}", e)

        return {"ok": True, "name": name}
