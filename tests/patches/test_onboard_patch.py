"""Tests for c_onboard_patch — onboard refresh compatibility."""

from __future__ import annotations

import importlib
import json
from pathlib import Path

import pytest
from typer.testing import CliRunner


def _legacy_sidecar_config_payload(workspace: Path) -> dict:
    return {
        "agents": {
            "defaults": {
                "workspace": str(workspace),
                "model": "anthropic/claude-sonnet-4-6",
                "visionModel": "google/gemini-3.1-flash-lite-preview",
                "miniModel": "google/gemini-3.1-pro-preview",
                "voiceModel": None,
                "imageGenModel": "google/gemini-3.1-flash-image-preview",
                "maxTokens": 8192,
                "temperature": 0.8,
                "maxToolIterations": 100,
                "contextCompression": {
                    "enabled": True,
                    "maxChars": 50000,
                    "recentTurns": 10,
                    "minRecentTurns": 4,
                    "maxOldTurns": 4,
                    "enableHistoryLookupHint": True,
                    "protectedRecentMessages": 20,
                },
                "historySummarizer": {
                    "enabled": True,
                    "protectRecent": 6,
                    "toolResultMaxChars": 400,
                },
                "heartbeat": {
                    "enabled": True,
                    "interval_s": 3600,
                    "phrase1": {
                        "model": "google/gemini-3.1-flash-lite-preview",
                    },
                    "phrase2": {
                        "model": "google/gemini-3.1-pro-preview",
                    },
                },
            }
        },
        "channels": {
            "telegram": {
                "enabled": False,
                "token": "",
                "allowFrom": [],
                "proxy": "socks5://127.0.0.1:13659",
                "userTypingTimeout": 10,
                "transcriptionApiKey": "secret-transcription",
            }
        },
        "providers": {
            "zenmux": {
                "apiKey": "zenmux-key",
                "apiBase": "https://zenmux.ai/api/v1",
                "extraHeaders": None,
            },
            "yunwu": {
                "apiKey": "yunwu-key",
                "apiBase": "https://yunwu.ai/v1/messages",
                "extraHeaders": None,
            },
            "gemini": {
                "apiKey": "gemini-key",
                "apiBase": "https://zenmux.ai/api/v1",
                "extraHeaders": None,
            },
        },
        "gateway": {
            "host": "0.0.0.0",
            "port": 18790,
        },
        "tools": {
            "mcpServers": {},
            "web": {
                "proxy": "socks5://127.0.0.1:13659",
                "search": {
                    "provider": "duckduckgo",
                },
            },
            "exec": {
                "timeout": 300,
            },
            "claudeCode": {
                "enabled": True,
                "defaultProject": "/tmp/demo",
                "model": "claude-opus-4-6",
                "maxTurns": 100,
                "allowedTools": "Read,Edit,Bash",
                "timeout": 6000,
                "apiKey": "cc-key",
                "baseUrl": "https://zenmux.ai/api/anthropic",
            },
            "restrictToWorkspace": False,
            "restrictToConfigFile": True,
        },
        "token_stats": {
            "enabled": True,
            "record_full_request_payload": False,
        },
    }


@pytest.fixture()
def _reload_commands_module():
    import nanobot.cli.commands as cli_mod

    cli_mod = importlib.reload(cli_mod)
    yield cli_mod
    importlib.reload(cli_mod)


class TestOnboardPatch:
    def test_apply_onboard_patch_is_idempotent(self, _reload_commands_module):
        """T3.1: 二次 apply 应返回 skipped。"""
        from ava.patches.c_onboard_patch import apply_onboard_patch

        first = apply_onboard_patch()
        second = apply_onboard_patch()

        assert "wrapped" in first.lower() or "refresh" in first.lower()
        assert "skipped" in second.lower()

    def test_skip_when_onboard_command_missing(self, _reload_commands_module):
        """T3.2: onboard 命令不存在时应优雅跳过。"""
        import nanobot.cli.commands as cli_mod
        from ava.patches.c_onboard_patch import apply_onboard_patch

        cli_mod.app.registered_commands = []
        result = apply_onboard_patch()

        assert "skip" in result.lower()

    def test_refresh_preserves_existing_sidecar_shape(self, _reload_commands_module, monkeypatch, tmp_path: Path):
        """T3.3: refresh 应保留旧 sidecar 字段，不把 extra_config overlay 固化回 config.json。"""
        from ava.patches.a_schema_patch import apply_schema_patch
        from ava.patches.c_onboard_patch import apply_onboard_patch

        apply_schema_patch()
        apply_onboard_patch()

        config_path = tmp_path / "config.json"
        extra_config_path = tmp_path / "extra_config.json"
        workspace = tmp_path / "workspace"

        config_path.write_text(
            json.dumps(_legacy_sidecar_config_payload(workspace)),
            encoding="utf-8",
        )
        extra_config_path.write_text(
            json.dumps(
                {
                    "providers": {
                        "gemini": {
                            "apiBase": "https://zenmux.ai/api/vertex-ai/v1",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        monkeypatch.setattr("nanobot.channels.registry.discover_all", lambda: {})
        monkeypatch.setattr("nanobot.cli.commands.get_workspace_path", lambda _workspace=None: workspace)
        monkeypatch.setattr("nanobot.cli.commands.sync_workspace_templates", lambda _workspace: None)

        import nanobot.cli.commands as cli_mod

        runner = CliRunner()
        result = runner.invoke(cli_mod.app, ["onboard", "-c", str(config_path)], input="n\n")

        assert result.exit_code == 0

        saved = json.loads(config_path.read_text(encoding="utf-8"))

        assert saved["agents"]["defaults"]["voiceModel"] is None
        assert saved["agents"]["defaults"]["contextCompression"]["maxOldTurns"] == 4
        assert saved["agents"]["defaults"]["heartbeat"]["interval_s"] == 3600
        assert saved["tools"]["claudeCode"]["enabled"] is True
        assert saved["tools"]["restrictToConfigFile"] is True
        assert saved["channels"]["telegram"]["transcriptionApiKey"] == "secret-transcription"
        assert saved["providers"]["zenmux"]["apiBase"] == "https://zenmux.ai/api/v1"
        assert saved["providers"]["yunwu"]["apiBase"] == "https://yunwu.ai/v1/messages"
        assert saved["providers"]["gemini"]["apiBase"] == "https://zenmux.ai/api/v1"
        assert saved["token_stats"]["record_full_request_payload"] is False

        assert saved["api"]["host"] == "127.0.0.1"
        assert saved["gateway"]["console"]["enabled"] is True
        assert saved["providers"]["mistral"]["apiKey"] == ""

        extra_saved = json.loads(extra_config_path.read_text(encoding="utf-8"))
        assert extra_saved["providers"]["gemini"]["apiBase"] == "https://zenmux.ai/api/vertex-ai/v1"

    def test_wizard_save_preserves_existing_sidecar_shape(self, _reload_commands_module, monkeypatch, tmp_path: Path):
        """T3.4: wizard 保存现有配置时也应保留旧字段，且不固化 extra_config overlay。"""
        from ava.patches.a_schema_patch import apply_schema_patch
        from ava.patches.c_onboard_patch import apply_onboard_patch
        from nanobot.cli.onboard import OnboardResult

        apply_schema_patch()
        apply_onboard_patch()

        config_path = tmp_path / "config.json"
        extra_config_path = tmp_path / "extra_config.json"
        workspace = tmp_path / "workspace"

        config_path.write_text(
            json.dumps(_legacy_sidecar_config_payload(workspace)),
            encoding="utf-8",
        )
        extra_config_path.write_text(
            json.dumps(
                {
                    "providers": {
                        "gemini": {
                            "apiBase": "https://zenmux.ai/api/vertex-ai/v1",
                        }
                    }
                }
            ),
            encoding="utf-8",
        )

        monkeypatch.setattr(
            "nanobot.cli.onboard.run_onboard",
            lambda initial_config: OnboardResult(config=initial_config, should_save=True),
        )
        monkeypatch.setattr("nanobot.channels.registry.discover_all", lambda: {})
        monkeypatch.setattr("nanobot.cli.commands.get_workspace_path", lambda _workspace=None: workspace)
        monkeypatch.setattr("nanobot.cli.commands.sync_workspace_templates", lambda _workspace: None)

        import nanobot.cli.commands as cli_mod

        runner = CliRunner()
        result = runner.invoke(cli_mod.app, ["onboard", "--wizard", "-c", str(config_path)])

        assert result.exit_code == 0

        saved = json.loads(config_path.read_text(encoding="utf-8"))

        assert saved["agents"]["defaults"]["voiceModel"] is None
        assert saved["agents"]["defaults"]["heartbeat"]["interval_s"] == 3600
        assert saved["tools"]["claudeCode"]["enabled"] is True
        assert saved["channels"]["telegram"]["transcriptionApiKey"] == "secret-transcription"
        assert saved["providers"]["gemini"]["apiBase"] == "https://zenmux.ai/api/v1"
        assert saved["gateway"]["console"]["enabled"] is True
        assert saved["api"]["host"] == "127.0.0.1"

        extra_saved = json.loads(extra_config_path.read_text(encoding="utf-8"))
        assert extra_saved["providers"]["gemini"]["apiBase"] == "https://zenmux.ai/api/vertex-ai/v1"
