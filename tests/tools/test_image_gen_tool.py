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

        def get_provider_name(self, model: str):
            assert model == "google/gemini-3.1-flash-image-preview"
            return "google"

        def get_api_base(self, model: str):
            assert model == "google/gemini-3.1-flash-image-preview"
            return "https://vertex.example/v1"

    monkeypatch.setattr("nanobot.config.loader.load_config", lambda: FakeConfig())

    model, provider_name, api_key, api_base = _load_image_gen_config()

    assert model == "google/gemini-3.1-flash-image-preview"
    assert provider_name == "google"
    assert api_key == "secret-key"
    assert api_base == "https://vertex.example/v1"


def test_zenmux_openai_image_model_uses_generate_images(monkeypatch, tmp_path: Path):
    import ava.tools.image_gen as image_gen_module

    monkeypatch.setattr(
        image_gen_module,
        "_load_image_gen_config",
        lambda: ("openai/gpt-image-2", "openai", "secret-key", "https://zenmux.ai/api/v1"),
    )
    monkeypatch.setattr(image_gen_module, "_get_generated_dir", lambda: tmp_path)
    monkeypatch.setattr(image_gen_module, "_get_records_file", lambda: tmp_path / "records.jsonl")

    calls: list[dict] = []

    class FakeImage:
        def save(self, path: str) -> None:
            Path(path).write_bytes(b"png")

    class FakeModels:
        def generate_images(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(generated_images=[SimpleNamespace(image=FakeImage())])

        def generate_content(self, **kwargs):
            raise AssertionError("non-Google Zenmux image models must not use generate_content")

    monkeypatch.setattr(
        image_gen_module.ImageGenTool,
        "_get_client",
        lambda self: SimpleNamespace(models=FakeModels()),
    )

    tool = image_gen_module.ImageGenTool()
    result = asyncio.run(tool.execute(prompt="draw Rowlet writing code, transparent background"))

    assert "Generated image(s):" in result
    assert tool._provider_name == "zenmux"
    assert calls[0]["model"] == "openai/gpt-image-2"
    assert getattr(calls[0]["config"], "output_mime_type") == "image/png"
    assert len(list(tmp_path.glob("*.png"))) == 1


def test_google_image_model_still_uses_generate_content(monkeypatch, tmp_path: Path):
    import ava.tools.image_gen as image_gen_module

    monkeypatch.setattr(
        image_gen_module,
        "_load_image_gen_config",
        lambda: ("google/gemini-3.1-flash-image-preview", "google", "secret-key", "https://vertex.example/v1"),
    )
    monkeypatch.setattr(image_gen_module, "_get_generated_dir", lambda: tmp_path)
    monkeypatch.setattr(image_gen_module, "_get_records_file", lambda: tmp_path / "records.jsonl")

    calls: list[dict] = []

    class FakeImage:
        def save(self, path: str) -> None:
            Path(path).write_bytes(b"png")

    class FakePart:
        text = None
        inline_data = object()

        def as_image(self):
            return FakeImage()

    class FakeModels:
        def generate_content(self, **kwargs):
            calls.append(kwargs)
            return SimpleNamespace(parts=[FakePart()], usage_metadata=None)

        def generate_images(self, **kwargs):
            raise AssertionError("Google image models should keep using generate_content")

    monkeypatch.setattr(
        image_gen_module.ImageGenTool,
        "_get_client",
        lambda self: SimpleNamespace(models=FakeModels()),
    )

    tool = image_gen_module.ImageGenTool()
    result = asyncio.run(tool.execute(prompt="draw an owl avatar"))

    assert "Generated image(s):" in result
    assert calls[0]["model"] == "google/gemini-3.1-flash-image-preview"
    assert len(list(tmp_path.glob("*.png"))) == 1


def test_zenmux_base_normalizes_to_vertex_endpoint():
    from ava.tools.image_gen import _normalize_genai_base

    assert (
        _normalize_genai_base("https://zenmux.ai/api/v1", "zenmux")
        == "https://zenmux.ai/api/vertex-ai"
    )


def test_execute_reports_missing_google_genai_dependency(monkeypatch, tmp_path: Path):
    import ava.tools.image_gen as image_gen_module

    monkeypatch.setattr(
        image_gen_module,
        "_load_image_gen_config",
        lambda: ("google/gemini-3.1-flash-image-preview", "google", "secret-key", "https://vertex.example/v1"),
    )
    monkeypatch.setattr(image_gen_module, "_get_generated_dir", lambda: tmp_path)
    monkeypatch.setattr(image_gen_module, "_get_records_file", lambda: tmp_path / "records.jsonl")

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
