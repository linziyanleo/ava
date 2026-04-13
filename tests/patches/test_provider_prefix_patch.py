"""Tests for provider_prefix_patch sidecar model-prefix compatibility."""

from __future__ import annotations

from types import SimpleNamespace

import pytest


@pytest.fixture(autouse=True)
def _restore_build_kwargs():
    """每个用例后恢复原始 _build_kwargs，避免污染其他 patch 测试。"""
    from nanobot.providers.openai_compat_provider import OpenAICompatProvider

    original = getattr(
        OpenAICompatProvider,
        "_ava_original_build_kwargs",
        OpenAICompatProvider._build_kwargs,
    )
    yield
    OpenAICompatProvider._build_kwargs = original
    if hasattr(OpenAICompatProvider, "_ava_original_build_kwargs"):
        delattr(OpenAICompatProvider, "_ava_original_build_kwargs")


class TestProviderPrefixPatch:
    def test_strip_yunwu_prefix_from_default_model(self):
        """T1: 无 spec 且 default_model 带 yunwu 前缀时，应剥离后再发请求。"""
        from ava.patches.provider_prefix_patch import apply_provider_prefix_patch
        from nanobot.providers.openai_compat_provider import OpenAICompatProvider

        apply_provider_prefix_patch()
        provider = OpenAICompatProvider(
            api_key="test-key",
            api_base="https://example.com/v1",
            default_model="yunwu/claude-opus-4-6",
        )

        kwargs = provider._build_kwargs(
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            model=None,
            max_tokens=16,
            temperature=1.0,
            reasoning_effort=None,
            tool_choice=None,
        )

        assert kwargs["model"] == "claude-opus-4-6"

    def test_strip_zenmux_prefix_from_explicit_model(self):
        """T2: 无 spec 且显式传入 zenmux 前缀模型时，应剥离前缀。"""
        from ava.patches.provider_prefix_patch import apply_provider_prefix_patch
        from nanobot.providers.openai_compat_provider import OpenAICompatProvider

        apply_provider_prefix_patch()
        provider = OpenAICompatProvider(
            api_key="test-key",
            api_base="https://example.com/v1",
            default_model="gpt-4o-mini",
        )

        kwargs = provider._build_kwargs(
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            model="zenmux/gemini-3.1-flash-lite-preview",
            max_tokens=16,
            temperature=1.0,
            reasoning_effort=None,
            tool_choice=None,
        )

        assert kwargs["model"] == "gemini-3.1-flash-lite-preview"

    def test_keep_plain_model_when_no_sidecar_prefix(self):
        """T3: 无 sidecar 前缀的普通模型名不应被修改。"""
        from ava.patches.provider_prefix_patch import apply_provider_prefix_patch
        from nanobot.providers.openai_compat_provider import OpenAICompatProvider

        apply_provider_prefix_patch()
        provider = OpenAICompatProvider(
            api_key="test-key",
            api_base="https://example.com/v1",
            default_model="gpt-4.1-mini",
        )

        kwargs = provider._build_kwargs(
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            model=None,
            max_tokens=16,
            temperature=1.0,
            reasoning_effort=None,
            tool_choice=None,
        )

        assert kwargs["model"] == "gpt-4.1-mini"

    def test_preserve_spec_managed_strip_behavior(self):
        """T4: 已有 spec 的 provider 仍应沿用原始 strip_model_prefix 逻辑。"""
        from ava.patches.provider_prefix_patch import apply_provider_prefix_patch
        from nanobot.providers.openai_compat_provider import OpenAICompatProvider

        apply_provider_prefix_patch()
        spec = SimpleNamespace(
            name="aihubmix",
            env_key="OPENAI_API_KEY",
            default_api_base="https://example.com/v1",
            supports_prompt_caching=False,
            strip_model_prefix=True,
            supports_max_completion_tokens=False,
            model_overrides=(),
            is_gateway=True,
            env_extras=(),
        )
        provider = OpenAICompatProvider(
            api_key="test-key",
            api_base="https://example.com/v1",
            default_model="anthropic/claude-3-5-sonnet",
            spec=spec,
        )

        kwargs = provider._build_kwargs(
            messages=[{"role": "user", "content": "hi"}],
            tools=None,
            model=None,
            max_tokens=16,
            temperature=1.0,
            reasoning_effort=None,
            tool_choice=None,
        )

        assert kwargs["model"] == "claude-3-5-sonnet"

    def test_idempotent(self):
        """T5: 连续应用两次 patch 不应重复包裹方法。"""
        from ava.patches.provider_prefix_patch import apply_provider_prefix_patch

        first = apply_provider_prefix_patch()
        second = apply_provider_prefix_patch()

        assert "strips" in first
        assert "already patched" in second
