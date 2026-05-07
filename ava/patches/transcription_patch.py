"""Monkey patch 转写链路：保留 Groq 代理注入，并扩展 ZenMux/Gemini 多模态转译。

拦截点:
- ``GroqTranscriptionProvider.transcribe``
- ``ChannelManager._resolve_transcription_key``
- ``BaseChannel.transcribe_audio``

修改后行为:
- 继续为 Groq Whisper 请求注入 ``tools.web.proxy``
- 允许 ``channels.transcriptionProvider`` 使用 ``gemini`` / ``zenmux``
- ``gemini`` / ``zenmux`` 走 ZenMux Vertex ``generateContent``，默认模型为
  ``google/gemini-2.5-flash-lite``
"""

from __future__ import annotations

import base64
import mimetypes
from pathlib import Path
from typing import Any

import httpx
from loguru import logger

from ava.launcher import register_patch
from ava.runtime import config_overlay
from ava.runtime import paths as runtime_paths

_ZENMUX_VERTEX_BASE_URL = "https://zenmux.ai/api/vertex-ai/v1"
_ZENMUX_TRANSCRIPTION_MODEL = "google/gemini-2.5-flash-lite"
_MIME_TYPE_ALIASES = {
    "audio/x-wav": "audio/wav",
}


def _normalize_transcription_provider(provider: str | None) -> str:
    """统一 transcription provider 名称。"""
    return (provider or "").strip().lower().replace("-", "_")


def _read_proxy_from_raw_config() -> str | None:
    """从有效配置里读取 web proxy。"""
    try:
        data = config_overlay.load_effective_config_data(runtime_paths.get_config_path())
        return data.get("tools", {}).get("web", {}).get("proxy") or None
    except Exception as exc:
        logger.warning("transcription_patch: failed to read proxy config: {}", exc)
    return None


def _load_runtime_config() -> Any | None:
    """加载 runtime config，并解析 env 引用。"""
    try:
        from nanobot.config.loader import load_config, resolve_config_env_vars

        return resolve_config_env_vars(
            load_config(runtime_paths.resolve_ava_home() / "config.json")
        )
    except Exception as exc:
        logger.warning("transcription_patch: failed to load runtime config: {}", exc)
        return None


def _normalize_vertex_api_base(api_base: str | None) -> str | None:
    """归一化 ZenMux Vertex API base。"""
    base = (api_base or "").strip().rstrip("/")
    if not base:
        return None
    if "zenmux.ai" in base and "/vertex-ai/" not in base:
        if base.endswith("/api/v1"):
            return f"{base[:-3]}/vertex-ai/v1"
        if base.endswith("/api"):
            return f"{base}/vertex-ai/v1"
    if base.endswith("/v1"):
        return base
    return f"{base}/v1"


def _resolve_multimodal_transcription_config(
    provider: str | None,
) -> tuple[str | None, str | None, str]:
    """解析 gemini / zenmux 多模态转译配置。

    ``zenmux`` 优先读 ``providers.zenmux``，缺失时回退到当前 sidecar 常用的
    ``providers.gemini`` + ZenMux Vertex base 配置。
    """
    normalized = _normalize_transcription_provider(provider)
    cfg = _load_runtime_config()
    if cfg is None:
        return None, None, _ZENMUX_TRANSCRIPTION_MODEL

    providers = getattr(cfg, "providers", None)
    if providers is None:
        return None, None, _ZENMUX_TRANSCRIPTION_MODEL

    if normalized == "zenmux":
        zenmux_cfg = getattr(providers, "zenmux", None)
        zenmux_key = getattr(zenmux_cfg, "api_key", "") if zenmux_cfg else ""
        zenmux_base = getattr(zenmux_cfg, "api_base", None) if zenmux_cfg else None
        if zenmux_key or zenmux_base:
            return (
                zenmux_key or None,
                _normalize_vertex_api_base(zenmux_base or _ZENMUX_VERTEX_BASE_URL),
                _ZENMUX_TRANSCRIPTION_MODEL,
            )

    gemini_cfg = getattr(providers, "gemini", None)
    gemini_key = getattr(gemini_cfg, "api_key", "") if gemini_cfg else ""
    gemini_base = getattr(gemini_cfg, "api_base", None) if gemini_cfg else None
    return (
        gemini_key or None,
        _normalize_vertex_api_base(gemini_base),
        _ZENMUX_TRANSCRIPTION_MODEL,
    )


def _resolve_runtime_proxy() -> str | None:
    """读取 runtime config 中的通用网络代理。"""
    cfg = _load_runtime_config()
    if cfg is None:
        return None
    tools = getattr(cfg, "tools", None)
    web = getattr(tools, "web", None) if tools is not None else None
    return getattr(web, "proxy", None) if web is not None else None


def _extract_vertex_text(payload: dict[str, Any]) -> str:
    """从 Vertex generateContent 响应中提取文本。"""
    candidates = payload.get("candidates") or []
    for candidate in candidates:
        content = candidate.get("content") or {}
        parts = content.get("parts") or []
        texts = [
            part.get("text", "").strip()
            for part in parts
            if isinstance(part, dict) and part.get("text")
        ]
        if texts:
            return "\n".join(texts).strip()
    return ""


async def _transcribe_with_zenmux_multimodal(
    *,
    api_key: str,
    api_base: str,
    model: str,
    file_path: str | Path,
    proxy: str | None,
) -> str:
    """通过 ZenMux Vertex generateContent 做音频转文本。"""
    path = Path(file_path)
    if not path.exists():
        logger.error("Audio file not found: {}", file_path)
        return ""

    mime_type = mimetypes.guess_type(path.name, strict=False)[0] or "audio/wav"
    mime_type = _MIME_TYPE_ALIASES.get(mime_type, mime_type)
    payload = {
        "contents": [
            {
                "role": "user",
                "parts": [
                    {
                        "text": (
                            "Transcribe the speech in this audio. "
                            "Return only the plain transcript text. "
                            "Do not add commentary, timestamps, markdown, or speaker labels."
                        )
                    },
                    {
                        "inlineData": {
                            "mimeType": mime_type,
                            "data": base64.b64encode(path.read_bytes()).decode("ascii"),
                        }
                    },
                ],
            }
        ],
        "generationConfig": {
            "temperature": 0,
            "candidateCount": 1,
            "maxOutputTokens": 4096,
        },
    }

    client_kwargs: dict[str, Any] = {"timeout": 120.0}
    if proxy:
        client_kwargs["proxy"] = proxy

    endpoint = f"{api_base.rstrip('/')}/publishers/google/models/gemini-2.5-flash-lite:generateContent"
    try:
        async with httpx.AsyncClient(**client_kwargs) as client:
            response = await client.post(
                endpoint,
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json=payload,
            )
            response.raise_for_status()
            return _extract_vertex_text(response.json())
    except Exception as exc:
        logger.error(
            "ZenMux multimodal transcription error (model={}, base={}): {}",
            model,
            api_base,
            exc,
        )
        return ""


def apply_transcription_patch() -> str:
    """扩展转写链路：Groq 走代理，Gemini/ZenMux 走多模态 generateContent。"""
    from nanobot.channels.base import BaseChannel
    from nanobot.channels.manager import ChannelManager
    from nanobot.providers.transcription import GroqTranscriptionProvider

    descriptions: list[str] = []

    original_resolve_key = getattr(ChannelManager, "_resolve_transcription_key", None)
    if original_resolve_key is None:
        logger.warning(
            "transcription_patch skipped: ChannelManager._resolve_transcription_key not found"
        )
        descriptions.append("key routing skipped (ChannelManager._resolve_transcription_key missing)")
    elif not getattr(original_resolve_key, "_ava_transcription_key_router_patched", False):

        def patched_resolve_key(self, provider: str) -> str:
            normalized = _normalize_transcription_provider(provider)
            providers = getattr(self.config, "providers", None)
            if providers is None:
                return original_resolve_key(self, provider)

            if normalized == "gemini":
                gemini_cfg = getattr(providers, "gemini", None)
                return getattr(gemini_cfg, "api_key", "") if gemini_cfg is not None else ""

            if normalized == "zenmux":
                zenmux_cfg = getattr(providers, "zenmux", None)
                zenmux_key = getattr(zenmux_cfg, "api_key", "") if zenmux_cfg is not None else ""
                if zenmux_key:
                    return zenmux_key
                gemini_cfg = getattr(providers, "gemini", None)
                return getattr(gemini_cfg, "api_key", "") if gemini_cfg is not None else ""

            return original_resolve_key(self, provider)

        patched_resolve_key._ava_transcription_key_router_patched = True
        ChannelManager._resolve_transcription_key = patched_resolve_key
        descriptions.append("ChannelManager key routing supports gemini/zenmux")
    else:
        descriptions.append("ChannelManager key routing already patched (skipped)")

    original_transcribe_audio = getattr(BaseChannel, "transcribe_audio", None)
    if original_transcribe_audio is None:
        logger.warning("transcription_patch skipped: BaseChannel.transcribe_audio not found")
        descriptions.append("BaseChannel multimodal routing skipped (target missing)")
    elif not getattr(original_transcribe_audio, "_ava_multimodal_transcription_patched", False):

        async def patched_transcribe_audio(self, file_path: str | Path) -> str:
            provider = _normalize_transcription_provider(getattr(self, "transcription_provider", ""))
            if provider not in {"gemini", "zenmux"}:
                return await original_transcribe_audio(self, file_path)

            api_key = getattr(self, "transcription_api_key", "") or ""
            if not api_key:
                return ""

            _, api_base, model = _resolve_multimodal_transcription_config(provider)
            if not api_base:
                logger.warning(
                    "{}: multimodal transcription skipped because api_base is missing for provider {}",
                    getattr(self, "name", "channel"),
                    provider,
                )
                return ""

            proxy = _resolve_runtime_proxy()
            return await _transcribe_with_zenmux_multimodal(
                api_key=api_key,
                api_base=api_base,
                model=model,
                file_path=file_path,
                proxy=proxy,
            )

        patched_transcribe_audio._ava_multimodal_transcription_patched = True
        BaseChannel.transcribe_audio = patched_transcribe_audio
        descriptions.append("BaseChannel multimodal routing supports gemini/zenmux")
    else:
        descriptions.append("BaseChannel multimodal routing already patched (skipped)")

    original_transcribe = getattr(GroqTranscriptionProvider, "transcribe", None)
    if original_transcribe is None:
        logger.warning("transcription_patch skipped: GroqTranscriptionProvider.transcribe not found")
        descriptions.append("Groq proxy patch skipped (transcribe not found)")
        return "; ".join(descriptions)

    if getattr(original_transcribe, "_ava_transcription_patched", False):
        descriptions.append("Groq proxy already patched (skipped)")
        return "; ".join(descriptions)

    proxy = _read_proxy_from_raw_config()
    if not proxy:
        descriptions.append("Groq proxy patch skipped (no proxy configured)")
        return "; ".join(descriptions)

    async def patched_transcribe(self: GroqTranscriptionProvider, file_path: str | Path) -> str:
        if not self.api_key:
            logger.warning("Groq API key not configured for transcription")
            return ""

        path = Path(file_path)
        if not path.exists():
            logger.error("Audio file not found: {}", file_path)
            return ""

        try:
            async with httpx.AsyncClient(proxy=proxy, timeout=60.0) as client:
                with open(path, "rb") as file:
                    files = {
                        "file": (path.name, file),
                        "model": (None, "whisper-large-v3"),
                    }
                    response = await client.post(
                        self.api_url,
                        headers={"Authorization": f"Bearer {self.api_key}"},
                        files=files,
                    )
                    response.raise_for_status()
                    data = response.json()
                    return data.get("text", "")
        except Exception as exc:
            logger.error("Groq transcription error (proxy={}): {}", proxy, exc)
            return ""

    patched_transcribe._ava_transcription_patched = True
    GroqTranscriptionProvider.transcribe = patched_transcribe
    descriptions.append(f"GroqTranscriptionProvider.transcribe patched with proxy={proxy}")
    return "; ".join(descriptions)


register_patch("transcription_proxy", apply_transcription_patch)
