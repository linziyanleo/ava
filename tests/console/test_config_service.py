from __future__ import annotations

import json

from ava.console.services.config_service import ConfigService


def _write_legacy_config(root):
    payload = {
        "agents": {"defaults": {"model": "openai/gpt-5", "workspace": "/tmp/workspace"}},
        "channels": {"console": {"enabled": True}},
        "providers": {"openai": {"apiKey": "secret", "apiBase": None, "extraHeaders": None}},
        "gateway": {
            "host": "127.0.0.1",
            "port": 18790,
            "console": {
                "enabled": True,
                "port": 6688,
                "secretKey": "console-secret",
                "tokenExpireMinutes": 480,
            },
        },
        "tools": {"restrictToWorkspace": True, "restrictConfigFile": True},
        "token_stats": {"enabled": True, "record_full_request_payload": False},
    }
    (root / "config.json").write_text(json.dumps(payload), encoding="utf-8")
    return payload


def test_console_config_projection_excludes_nanobot_sections(tmp_path):
    _write_legacy_config(tmp_path)
    service = ConfigService(tmp_path)

    data = service.read_config("console-config.json", mask=False)
    parsed = json.loads(data["content"])

    assert data["mtime"] == 0
    assert parsed == {
        "gateway": {
            "host": "127.0.0.1",
            "port": 18790,
            "console": {
                "enabled": True,
                "port": 6688,
                "secretKey": "console-secret",
                "tokenExpireMinutes": 480,
            },
        }
    }
    assert "agents" not in parsed
    assert "providers" not in parsed
    assert "tools" not in parsed


def test_console_config_persists_independently_after_first_write(tmp_path):
    _write_legacy_config(tmp_path)
    service = ConfigService(tmp_path)
    content = json.dumps({"gateway": {"host": "0.0.0.0", "port": 18790}})

    result = service.update_config("console-config.json", content, expected_mtime=0)
    (tmp_path / "config.json").unlink()
    data = service.read_config("console-config.json", mask=False)

    assert result["mtime"] > 0
    assert json.loads(data["content"]) == {"gateway": {"host": "0.0.0.0", "port": 18790}}


def test_nanobot_config_alias_keeps_legacy_config_compatible(tmp_path):
    payload = _write_legacy_config(tmp_path)
    service = ConfigService(tmp_path)

    data = service.read_config("nanobot-config.json", mask=False)

    assert json.loads(data["content"]) == payload


def test_backend_schema_names_console_and_nanobot_configs_separately():
    from ava.forks.config import schema

    assert issubclass(schema.Config, schema.NanobotConfig)
    assert "console" in schema.GatewayConfig.model_fields
    assert "agents" in schema.NanobotConfig.model_fields
    assert "providers" in schema.NanobotConfig.model_fields
    assert "tools" in schema.NanobotConfig.model_fields
    assert "agents" not in schema.ConsoleConfig.model_fields
    assert "providers" not in schema.ConsoleConfig.model_fields
    assert "tools" not in schema.ConsoleConfig.model_fields


def test_agent_specific_configs_are_separate_from_console_config(tmp_path):
    service = ConfigService(tmp_path)

    codex_template = service.read_config("codex-config.toml", mask=False)
    claude_template = service.read_config("claude-code-settings.json", mask=False)
    image_template = service.read_config("image-gen-config.json", mask=False)

    assert codex_template["mtime"] == 0
    assert codex_template["format"] == "toml"
    assert "model" in codex_template["content"]
    assert claude_template["format"] == "json"
    assert image_template["format"] == "json"

    service.update_config("codex-config.toml", 'model = "gpt-5"\n', expected_mtime=0)
    service.update_config(
        "claude-code-settings.json",
        json.dumps({"model": "claude-sonnet-4"}),
        expected_mtime=0,
    )

    assert (tmp_path / "console" / "agents" / "codex" / "config.toml").read_text(encoding="utf-8") == 'model = "gpt-5"\n'
    assert json.loads((tmp_path / "console" / "agents" / "claude_code" / "settings.json").read_text(encoding="utf-8")) == {
        "model": "claude-sonnet-4",
    }
    assert not (tmp_path / "console" / "console-config.json").exists()
