"""Monkey patch OpenAI-compatible provider to strip sidecar model prefixes.

拦截点: ``OpenAICompatProvider._build_kwargs``
原始行为: 当 sidecar 私有 provider 没有 registry spec 时，会把 ``yunwu/...``、
``zenmux/...`` 原样发送给 OpenAI-compatible 网关。
修改后行为: 对缺少 spec 的 sidecar provider，在真正发请求前剥离模型前缀，
从而兼容旧版 ``.nanobot`` 配置里的 ``yunwu/...`` / ``zenmux/...`` 写法。

DEPRECATION: 待 sidecar 网关配置全部迁移到 ProviderSpec 后删除本 patch。
"""

from __future__ import annotations

from functools import wraps

from loguru import logger

from ava.launcher import register_patch

_SIDECAR_MODEL_PREFIXES = ("yunwu/", "zenmux/")


def _strip_sidecar_prefix(model: str | None) -> str | None:
    """剥离 sidecar 私有 provider 的模型前缀。"""
    if not isinstance(model, str):
        return model

    lowered = model.lower()
    for prefix in _SIDECAR_MODEL_PREFIXES:
        if lowered.startswith(prefix):
            return model.split("/", 1)[1]
    return model


def apply_provider_prefix_patch() -> str:
    """为缺少 registry spec 的 sidecar provider 补齐模型前缀剥离逻辑。"""
    from nanobot.providers.openai_compat_provider import OpenAICompatProvider

    original_build_kwargs = getattr(OpenAICompatProvider, "_build_kwargs", None)
    if original_build_kwargs is None:
        logger.warning(
            "provider_prefix_patch skipped: OpenAICompatProvider._build_kwargs not found"
        )
        return "provider_prefix_patch skipped (target method not found)"

    if getattr(original_build_kwargs, "_ava_sidecar_prefix_patch", False):
        return "sidecar model prefix strip already patched (skipped)"

    if not hasattr(OpenAICompatProvider, "_ava_original_build_kwargs"):
        OpenAICompatProvider._ava_original_build_kwargs = original_build_kwargs

    @wraps(original_build_kwargs)
    def patched_build_kwargs(
        self,
        messages,
        tools,
        model,
        max_tokens,
        temperature,
        reasoning_effort,
        tool_choice,
    ):
        # DEPRECATION: 仅为旧版 yunwu/zenmux 前缀配置保留，迁移完成后可删除。
        # 只有 sidecar 私有 provider 缺少 spec 时才做兼容，避免影响上游 provider。
        normalized_model = model
        if getattr(self, "_spec", None) is None:
            fallback_model = model or getattr(self, "default_model", None)
            stripped_model = _strip_sidecar_prefix(fallback_model)
            if stripped_model != fallback_model:
                normalized_model = stripped_model

        return original_build_kwargs(
            self,
            messages,
            tools,
            normalized_model,
            max_tokens,
            temperature,
            reasoning_effort,
            tool_choice,
        )

    patched_build_kwargs._ava_sidecar_prefix_patch = True
    OpenAICompatProvider._build_kwargs = patched_build_kwargs
    return "OpenAICompatProvider strips yunwu/zenmux model prefixes for sidecar gateways"


register_patch("provider_prefix_compat", apply_provider_prefix_patch)
