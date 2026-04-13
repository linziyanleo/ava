"""Skills and tools management service.

Manages three skill sources:
  1. ava/skills/   — sidecar custom skills (install target)
  2. .agents/      — external agent skills (read-only discovery)
  3. nanobot/skills/ — upstream builtin (read-only)

Enabled/disabled state is persisted in SQLite ``skill_config`` table.
"""

from __future__ import annotations

import re
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from ava.storage.database import Database


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
