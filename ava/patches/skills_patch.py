"""Patch SkillsLoader to support three-source discovery and SQLite-backed enable/disable.

Sources (in priority order):
  1. workspace/skills/     — runtime workspace skills (original)
  2. ava/skills/           — sidecar custom skills (replaces builtin_skills)
  3. .agents/*/            — external agent skills (symlinks or real dirs)
  4. nanobot/skills/       — upstream builtin (fallback for skills not in ava/)

Disabled skills (stored in SQLite skill_config table) are filtered out of
list_skills() so they never appear in the agent context.
"""

from __future__ import annotations

from pathlib import Path

from loguru import logger

from ava.adapters.nanobot.discovery import resolve_nanobot_checkout
from ava.launcher import register_patch

# Resolved once at import time
_AVA_SKILLS_DIR = Path(__file__).parent.parent / "skills"
_AGENTS_SKILLS_DIR = Path.home() / ".agents" / "skills"


def _get_nanobot_skills_dir() -> Path:
    return resolve_nanobot_checkout().skills_dir


def _get_db():
    """Lazily obtain the Database singleton (available after storage_patch)."""
    try:
        from ava.storage import get_db
        return get_db()
    except Exception:
        return None


def _get_disabled_skills() -> set[str]:
    """Query SQLite for disabled skill names."""
    db = _get_db()
    if db is None:
        return set()
    try:
        rows = db.fetchall("SELECT name FROM skill_config WHERE enabled = 0")
        return {row["name"] for row in rows}
    except Exception:
        return set()


def apply_skills_patch() -> str:
    from nanobot.agent.skills import SkillsLoader

    missing = [
        method_name
        for method_name in ("__init__", "list_skills", "load_skill")
        if not hasattr(SkillsLoader, method_name)
    ]
    if missing:
        logger.warning(
            "skills_patch skipped: SkillsLoader missing methods {}",
            ", ".join(missing),
        )
        return f"skills_patch skipped (missing methods: {', '.join(missing)})"

    if getattr(SkillsLoader.load_skill, "_ava_skills_patched", False):
        return "skills_patch already applied (skipped)"

    original_init = SkillsLoader.__init__
    original_list = SkillsLoader.list_skills
    original_load = SkillsLoader.load_skill

    # ------------------------------------------------------------------
    # Patch __init__: redirect builtin_skills to ava/skills/ so ava
    # overrides nanobot/skills/ for same-named skills. Save the original
    # nanobot builtin dir for fallback.
    # ------------------------------------------------------------------
    def patched_init(self, workspace: Path, builtin_skills_dir: Path | None = None):
        # Save original nanobot builtin dir before overriding
        self._nanobot_skills = builtin_skills_dir or _get_nanobot_skills_dir()
        # Override builtin_skills to ava/skills/ — this makes the original
        # list_skills() scan ava/ instead of nanobot/, giving ava priority.
        original_init(self, workspace, _AVA_SKILLS_DIR)
        self._agents_dir = _AGENTS_SKILLS_DIR

    # ------------------------------------------------------------------
    # Patch list_skills: append .agents/ + nanobot/ fallback + disabled filter
    # ------------------------------------------------------------------
    def patched_list_skills(self, filter_unavailable: bool = True) -> list[dict]:
        # Original now scans: workspace/skills/ → ava/skills/ (due to patched init)
        skills = original_list(self, filter_unavailable)
        seen = {s["name"] for s in skills}

        # Relabel ava/skills/ entries from "builtin" to "ava"
        for s in skills:
            if s.get("source") == "builtin":
                s["source"] = "ava"

        # Add .agents/
        agents_dir = getattr(self, "_agents_dir", _AGENTS_SKILLS_DIR)
        if agents_dir.exists():
            for skill_dir in sorted(agents_dir.iterdir()):
                resolved = skill_dir.resolve() if skill_dir.is_symlink() else skill_dir
                if resolved.is_dir() and skill_dir.name not in seen and skill_dir.name != "__pycache__":
                    skill_file = resolved / "SKILL.md"
                    if skill_file.exists():
                        entry = {"name": skill_dir.name, "path": str(skill_file), "source": "agents"}
                        if not filter_unavailable or self._check_requirements(self._get_skill_meta(skill_dir.name)):
                            skills.append(entry)
                            seen.add(skill_dir.name)

        # Add nanobot/skills/ as fallback (only skills not already found)
        nanobot_dir = getattr(self, "_nanobot_skills", _get_nanobot_skills_dir())
        if nanobot_dir and nanobot_dir.exists():
            for skill_dir in sorted(nanobot_dir.iterdir()):
                if skill_dir.is_dir() and skill_dir.name not in seen and skill_dir.name != "__pycache__":
                    skill_file = skill_dir / "SKILL.md"
                    if skill_file.exists():
                        entry = {"name": skill_dir.name, "path": str(skill_file), "source": "builtin"}
                        if not filter_unavailable or self._check_requirements(self._get_skill_meta(skill_dir.name)):
                            skills.append(entry)
                            seen.add(skill_dir.name)

        # Filter disabled
        disabled = _get_disabled_skills()
        if disabled:
            skills = [s for s in skills if s["name"] not in disabled]

        return skills

    # ------------------------------------------------------------------
    # Patch load_skill: search ava/skills/ (via original), .agents/, nanobot/
    # ------------------------------------------------------------------
    def patched_load_skill(self, name: str) -> str | None:
        # Check disabled first
        disabled = _get_disabled_skills()
        if name in disabled:
            return None

        # Original now checks: workspace → ava/skills/ (due to patched init)
        result = original_load(self, name)
        if result is not None:
            return result

        # .agents/
        agents_dir = getattr(self, "_agents_dir", _AGENTS_SKILLS_DIR)
        agents_skill = agents_dir / name
        if agents_skill.exists():
            resolved = agents_skill.resolve() if agents_skill.is_symlink() else agents_skill
            skill_file = resolved / "SKILL.md"
            if skill_file.exists():
                return skill_file.read_text(encoding="utf-8")

        # nanobot/skills/ fallback
        nanobot_dir = getattr(self, "_nanobot_skills", _get_nanobot_skills_dir())
        if nanobot_dir:
            nanobot_skill = nanobot_dir / name / "SKILL.md"
            if nanobot_skill.exists():
                return nanobot_skill.read_text(encoding="utf-8")

        return None

    patched_init._ava_skills_patched = True
    patched_list_skills._ava_skills_patched = True
    patched_load_skill._ava_skills_patched = True
    SkillsLoader.__init__ = patched_init
    SkillsLoader.list_skills = patched_list_skills
    SkillsLoader.load_skill = patched_load_skill

    return "SkillsLoader: 3-source discovery (ava/skills/ > .agents/ > nanobot/skills/) + SQLite disabled filter"


register_patch("skills_loader", apply_skills_patch)
