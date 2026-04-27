"""Tests for ava.runtime.config_overlay."""

from __future__ import annotations

import json
from pathlib import Path


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


def test_load_effective_config_data_merges_legacy_overlay_and_extra(monkeypatch, tmp_path: Path):
    from ava.runtime import config_overlay

    fake_home = tmp_path / "home"
    ava_home = fake_home / ".ava"
    legacy_home = fake_home / ".nanobot"
    fake_home.mkdir()
    monkeypatch.setenv("AVA_HOME", str(ava_home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    _write_json(
        legacy_home / "config.json",
        {
            "agents": {"defaults": {"model": "anthropic/base-model"}},
            "gateway": {"port": 18790},
            "tools": {"web": {"proxy": "http://legacy-proxy"}},
        },
    )
    _write_json(
        ava_home / "config.json",
        {
            "agents": {"defaults": {"visionModel": "google/gemini-3.1-flash-lite-preview"}},
            "token_stats": {"enabled": True},
        },
    )
    _write_json(
        ava_home / "extra_config.json",
        {
            "tools": {"claudeCode": {"model": "claude-opus-4-6"}},
            "providers": {"zenmux": {"apiBase": "https://zenmux.ai/api/v1"}},
        },
    )

    merged = config_overlay.load_effective_config_data(ava_home / "config.json")

    assert merged["agents"]["defaults"]["model"] == "anthropic/base-model"
    assert (
        merged["agents"]["defaults"]["visionModel"]
        == "google/gemini-3.1-flash-lite-preview"
    )
    assert merged["tools"]["web"]["proxy"] == "http://legacy-proxy"
    assert merged["tools"]["claudeCode"]["model"] == "claude-opus-4-6"
    assert merged["providers"]["zenmux"]["apiBase"] == "https://zenmux.ai/api/v1"
    assert merged["token_stats"]["enabled"] is True


def test_normalize_config_overlay_strips_legacy_and_extra_duplicates(monkeypatch, tmp_path: Path):
    from ava.runtime import config_overlay

    fake_home = tmp_path / "home"
    ava_home = fake_home / ".ava"
    legacy_home = fake_home / ".nanobot"
    fake_home.mkdir()
    monkeypatch.setenv("AVA_HOME", str(ava_home))
    monkeypatch.setattr(Path, "home", classmethod(lambda cls: fake_home))

    _write_json(
        legacy_home / "config.json",
        {
            "agents": {"defaults": {"model": "anthropic/base-model"}},
            "providers": {"openai": {"apiKey": "legacy-key"}},
            "tools": {"web": {"proxy": None}},
        },
    )
    _write_json(
        ava_home / "extra_config.json",
        {
            "tools": {"claudeCode": {"model": "claude-opus-4-6"}},
        },
    )
    _write_json(
        ava_home / "config.json",
        {
            "agents": {
                "defaults": {
                    "model": "anthropic/base-model",
                    "visionModel": "google/gemini-3.1-flash-lite-preview",
                }
            },
            "providers": {"openai": {"apiKey": "legacy-key"}},
            "tools": {
                "web": {"proxy": None},
                "claudeCode": {"model": "claude-opus-4-6"},
                "restrictToConfigFile": True,
            },
            "token_stats": {"enabled": True},
        },
    )

    overlay = config_overlay.normalize_config_overlay(ava_home / "config.json")
    saved = json.loads((ava_home / "config.json").read_text(encoding="utf-8"))

    assert saved == overlay
    assert "providers" not in saved
    assert saved["agents"]["defaults"]["visionModel"] == "google/gemini-3.1-flash-lite-preview"
    assert saved["tools"]["restrictToConfigFile"] is True
    assert "claudeCode" not in saved["tools"]
    assert saved["token_stats"]["enabled"] is True
