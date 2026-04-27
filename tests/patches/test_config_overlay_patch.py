"""Tests for bb_config_overlay_patch."""

from __future__ import annotations

import importlib
import json
import sys
from pathlib import Path

import pytest


def _write_json(path: Path, data: dict) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, ensure_ascii=False), encoding="utf-8")


@pytest.fixture(autouse=True)
def _restore_loader_and_patch_state(monkeypatch):
    import nanobot.config.loader as loader_mod

    original_load = loader_mod.load_config
    monkeypatch.setattr(loader_mod, "_current_config_path", None, raising=False)

    yield

    monkeypatch.setattr(loader_mod, "load_config", original_load, raising=False)
    monkeypatch.setattr(loader_mod, "_current_config_path", None, raising=False)

    patch_mod = sys.modules.get("ava.patches.bb_config_overlay_patch")
    if patch_mod is not None:
        monkeypatch.setattr(patch_mod, "_PATCHED", False, raising=False)
        importlib.reload(patch_mod)


def test_load_config_merges_legacy_overlay_and_extra(monkeypatch, tmp_path: Path):
    from ava.patches.a_schema_patch import apply_schema_patch
    from ava.patches.bb_config_overlay_patch import apply_config_overlay_patch
    import nanobot.config.loader as loader_mod

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
            "providers": {"openai": {"apiKey": "legacy-openai-key"}},
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
        },
    )

    apply_schema_patch()
    apply_config_overlay_patch()
    loader_mod.set_config_path(ava_home / "config.json")

    config = loader_mod.load_config()

    assert config.agents.defaults.model == "anthropic/base-model"
    assert config.agents.defaults.vision_model == "google/gemini-3.1-flash-lite-preview"
    assert config.providers.openai.api_key == "legacy-openai-key"
    assert config.tools.claude_code.model == "claude-opus-4-6"
    assert config.token_stats.enabled is True


def test_apply_is_idempotent():
    from ava.patches.bb_config_overlay_patch import apply_config_overlay_patch

    first = apply_config_overlay_patch()
    second = apply_config_overlay_patch()

    assert "overlay" in first.lower()
    assert "skipped" in second.lower()
