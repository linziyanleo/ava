"""Tests for the image generation tool config loading and runtime failures."""

from __future__ import annotations

import asyncio
import builtins
from pathlib import Path
from types import SimpleNamespace


def test_load_image_gen_config_reads_model_and_provider(monkeypatch):
    from ava.tools.image_gen import _load_image_gen_config

    provider = SimpleNamespace(api_key="secret-key", api_base="https://provider.example/v1")

    class FakeConfig:
        def __init__(self) -> None:
            self.agents = SimpleNamespace(
                defaults=SimpleNamespace(image_gen_model="google/gemini-3.1-flash-image-preview")
            )

        def get_provider(self, model: str):
            assert model == "google/gemini-3.1-flash-image-preview"
            return provider

        def get_api_base(self, model: str):
            assert model == "google/gemini-3.1-flash-image-preview"
            return "https://vertex.example/v1"

    monkeypatch.setattr("nanobot.config.loader.load_config", lambda: FakeConfig())

    model, api_key, api_base = _load_image_gen_config()

    assert model == "google/gemini-3.1-flash-image-preview"
    assert api_key == "secret-key"
    assert api_base == "https://vertex.example/v1"


def test_execute_reports_missing_google_genai_dependency(monkeypatch, tmp_path: Path):
    import ava.tools.image_gen as image_gen_module

    monkeypatch.setattr(
        image_gen_module,
        "_load_image_gen_config",
        lambda: ("google/gemini-3.1-flash-image-preview", "secret-key", "https://vertex.example/v1"),
    )
    monkeypatch.setattr(image_gen_module, "GENERATED_DIR", tmp_path)
    monkeypatch.setattr(image_gen_module, "RECORDS_FILE", tmp_path / "records.jsonl")

    tool = image_gen_module.ImageGenTool()

    original_import = builtins.__import__

    def fake_import(name, globals=None, locals=None, fromlist=(), level=0):
        if name == "google.genai":
            raise ModuleNotFoundError("No module named 'google'")
        return original_import(name, globals, locals, fromlist, level)

    monkeypatch.setattr(builtins, "__import__", fake_import)

    result = asyncio.run(tool.execute(prompt="draw an owl avatar"))

    assert "Missing image generation dependency" in result
    assert "google" in result
