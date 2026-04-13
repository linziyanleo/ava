"""templates_patch 测试：收窄 workspace 模板覆盖边界。"""

from __future__ import annotations

from pathlib import Path

import pytest

_PROJECT_ROOT = Path(__file__).resolve().parents[2]


@pytest.fixture(autouse=True)
def _restore_sync_workspace_templates():
    """每个测试后恢复 sync_workspace_templates。"""
    import nanobot.cli.commands as commands_mod
    import nanobot.utils.helpers as helpers_mod

    original_helpers_sync = helpers_mod.sync_workspace_templates
    original_commands_sync = commands_mod.sync_workspace_templates
    yield
    helpers_mod.sync_workspace_templates = original_helpers_sync
    commands_mod.sync_workspace_templates = original_commands_sync


class TestTemplatesPatch:
    def test_apply_templates_patch_is_idempotent(self):
        """T12.1：重复 apply 应返回 skipped。"""
        from ava.patches.templates_patch import apply_templates_patch

        first = apply_templates_patch()
        second = apply_templates_patch()

        assert "TOOLS.md" in first or "接管" in first
        assert "skipped" in second.lower()

    def test_only_tools_is_force_overlaid(self, tmp_path: Path):
        """T12.2：每次同步只应强制覆盖 TOOLS.md。"""
        import nanobot.utils.helpers as helpers_mod
        from ava.patches.templates_patch import apply_templates_patch

        workspace = tmp_path / "workspace"
        workspace.mkdir(parents=True)
        (workspace / "AGENTS.md").write_text("keep-agents", encoding="utf-8")
        (workspace / "SOUL.md").write_text("keep-soul", encoding="utf-8")
        (workspace / "USER.md").write_text("keep-user", encoding="utf-8")
        (workspace / "TOOLS.md").write_text("stale-tools", encoding="utf-8")
        (workspace / "HEARTBEAT.md").write_text("keep-heartbeat", encoding="utf-8")

        apply_templates_patch()
        helpers_mod.sync_workspace_templates(workspace, silent=True)

        assert (workspace / "AGENTS.md").read_text(encoding="utf-8") == "keep-agents"
        assert (workspace / "SOUL.md").read_text(encoding="utf-8") == "keep-soul"
        assert (workspace / "USER.md").read_text(encoding="utf-8") == "keep-user"
        assert (workspace / "HEARTBEAT.md").read_text(encoding="utf-8") == "keep-heartbeat"
        assert (workspace / "TOOLS.md").read_text(encoding="utf-8") == (
            (_PROJECT_ROOT / "ava" / "templates" / "TOOLS.md").read_text(encoding="utf-8")
        )

    def test_sidecar_only_templates_are_created_when_missing(self, tmp_path: Path):
        """T12.3：sidecar-only 模板缺失时仍应自动补建。"""
        import nanobot.utils.helpers as helpers_mod
        from ava.patches.templates_patch import apply_templates_patch

        workspace = tmp_path / "workspace"

        apply_templates_patch()
        added = helpers_mod.sync_workspace_templates(workspace, silent=True)

        assert (workspace / "HEARTBEAT.md").is_file()
        assert "HEARTBEAT.md" in added
