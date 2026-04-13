"""Tests for skills_patch — SkillsLoader source extension and disabled filter."""

from pathlib import Path

import pytest

from nanobot.agent.skills import SkillsLoader


@pytest.fixture(autouse=True)
def _restore_skills_loader():
    """Save and restore SkillsLoader methods."""
    orig_init = SkillsLoader.__init__
    orig_list = SkillsLoader.list_skills
    orig_load = SkillsLoader.load_skill
    yield
    SkillsLoader.__init__ = orig_init
    SkillsLoader.list_skills = orig_list
    SkillsLoader.load_skill = orig_load


class TestSkillsPatch:
    def test_patch_applies_without_error(self):
        """T10.1: apply_skills_patch runs without error."""
        from ava.patches.skills_patch import apply_skills_patch

        result = apply_skills_patch()
        assert "skillsloader" in result.lower() or "3-source" in result.lower()

    def test_idempotent(self):
        """T10.2: repeated apply returns skipped."""
        from ava.patches.skills_patch import apply_skills_patch

        apply_skills_patch()
        result = apply_skills_patch()
        assert "skipped" in result.lower()

    def test_loader_methods_replaced(self):
        """T10.3: __init__/list_skills/load_skill are replaced."""
        from ava.patches.skills_patch import apply_skills_patch

        orig_init = SkillsLoader.__init__
        orig_list = SkillsLoader.list_skills
        orig_load = SkillsLoader.load_skill

        apply_skills_patch()

        assert SkillsLoader.__init__ is not orig_init
        assert SkillsLoader.list_skills is not orig_list
        assert SkillsLoader.load_skill is not orig_load
