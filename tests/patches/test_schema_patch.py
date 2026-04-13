"""Tests for a_schema_patch — Config Schema Fork injection."""

import sys
from unittest.mock import patch

import pytest


@pytest.fixture(autouse=True)
def _clean_schema_module():
    """Remove fork marker before each test so patches can re-apply."""
    mod = sys.modules.get("nanobot.config.schema")
    if mod and getattr(mod, "_ava_fork", False):
        mod._ava_fork = False
    yield


class TestSchemaPatch:
    def test_fork_replaces_module(self):
        """T1.1: fork replaces sys.modules entry and sets _ava_fork marker."""
        from ava.patches.a_schema_patch import apply_schema_patch

        result = apply_schema_patch()
        mod = sys.modules["nanobot.config.schema"]
        assert getattr(mod, "_ava_fork", False) is True
        assert "replaced" in result.lower() or "fork" in result.lower()

    def test_extended_fields_exist(self):
        """T1.2: AgentDefaults instance has vision_model, mini_model etc."""
        from ava.patches.a_schema_patch import apply_schema_patch

        apply_schema_patch()
        from nanobot.config.schema import AgentDefaults

        inst = AgentDefaults()
        for field in ("vision_model", "mini_model", "image_gen_model"):
            assert hasattr(inst, field), f"Missing field: {field}"

    def test_console_config_exists(self):
        """T1.3: GatewayConfig has console field after fork."""
        from ava.patches.a_schema_patch import apply_schema_patch

        apply_schema_patch()
        from nanobot.config.schema import GatewayConfig

        assert "console" in GatewayConfig.model_fields

    def test_api_config_exists(self):
        """T1.3b: Config has api field after upstream API config sync."""
        from ava.patches.a_schema_patch import apply_schema_patch

        apply_schema_patch()
        from nanobot.config.schema import Config

        assert "api" in Config.model_fields

    def test_inherited_upstream_fields_exist(self):
        """T1.3c: 上游新增的 provider / MCP / web search 字段会自动继承进 fork。"""
        from ava.patches.a_schema_patch import apply_schema_patch

        apply_schema_patch()
        from nanobot.config.schema import MCPServerConfig, ProvidersConfig, WebSearchConfig

        assert "mistral" in ProvidersConfig.model_fields
        assert "ollama" in ProvidersConfig.model_fields
        assert "ovms" in ProvidersConfig.model_fields
        assert "stepfun" in ProvidersConfig.model_fields
        assert "byteplus" in ProvidersConfig.model_fields
        assert "byteplus_coding_plan" in ProvidersConfig.model_fields
        assert "volcengine_coding_plan" in ProvidersConfig.model_fields

        mcp = MCPServerConfig()
        assert "type" in MCPServerConfig.model_fields
        assert "enabled_tools" in MCPServerConfig.model_fields
        assert mcp.enabled_tools == ["*"]

        web_search = WebSearchConfig()
        assert "provider" in WebSearchConfig.model_fields
        assert "base_url" in WebSearchConfig.model_fields
        assert web_search.provider == "brave"

    def test_channels_keep_builtin_defaults_and_plugin_extras(self):
        """T1.3d: ChannelsConfig 既保留内建默认结构，也保留未知 plugin 节点。"""
        from ava.patches.a_schema_patch import apply_schema_patch

        apply_schema_patch()
        from nanobot.config.schema import ChannelsConfig

        cfg = ChannelsConfig.model_validate({
            "myplugin": {"enabled": True, "token": "abc"},
        })

        assert cfg.telegram.enabled is False
        assert getattr(cfg, "myplugin")["enabled"] is True

        dumped = cfg.model_dump(by_alias=True)
        assert dumped["telegram"]["enabled"] is False
        assert dumped["myplugin"]["token"] == "abc"

    def test_root_config_dump_keeps_sidecar_fields_after_upstream_preimport(self):
        """T1.3e: 即使上游 schema 已先被导入，根 Config dump 仍应导出 sidecar 字段。"""
        import importlib
        import nanobot.cli.commands as cli_mod
        from ava.patches.a_schema_patch import apply_schema_patch

        importlib.reload(cli_mod)
        apply_schema_patch()

        from nanobot.config.schema import Config

        dumped = Config().model_dump(mode="json", by_alias=True)

        assert dumped["agents"]["defaults"]["visionModel"] == "google/gemini-3.1-flash-lite-preview"
        assert dumped["agents"]["defaults"]["heartbeat"]["interval_s"] == 1800
        assert dumped["gateway"]["console"]["enabled"] is True
        assert dumped["tools"]["exec"]["autoVenv"] is True
        assert dumped["tools"]["claudeCode"]["model"] == "claude-sonnet-4-20250514"
        assert dumped["token_stats"]["record_full_request_payload"] is False

    def test_idempotent(self):
        """T1.4: calling apply twice does not error."""
        from ava.patches.a_schema_patch import apply_schema_patch

        r1 = apply_schema_patch()
        r2 = apply_schema_patch()
        assert "skipped" in r2.lower()

    def test_fork_file_missing(self):
        """T1.5: returns skip message when fork file doesn't exist."""
        from ava.patches.a_schema_patch import apply_schema_patch
        from pathlib import Path as RealPath

        # Remove _ava_fork marker so it attempts to apply
        mod = sys.modules.get("nanobot.config.schema")
        if mod:
            mod._ava_fork = False

        original_exists = RealPath.exists

        def fake_exists(self):
            if "forks/config/schema.py" in str(self):
                return False
            return original_exists(self)

        try:
            with patch.object(RealPath, "exists", fake_exists):
                result = apply_schema_patch()
            lowered = result.lower()
            assert "not found" in lowered or "skipped" in lowered or "reuse" in lowered
        finally:
            # Restore fork so subsequent tests aren't polluted
            if mod:
                mod._ava_fork = False
            apply_schema_patch()
