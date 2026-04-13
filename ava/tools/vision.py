"""Vision tool: analyze images from URLs or local paths using the LLM provider."""

import base64
import mimetypes
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.tools.base import Tool
from nanobot.providers.base import LLMProvider

class VisionTool(Tool):
    """Analyze images via the conversation LLM (vision-capable models)."""

    def __init__(
        self,
        provider: LLMProvider,
        model: str | None = None,
        token_stats: Any | None = None,
    ) -> None:
        self._provider = provider
        self._model = model
        self._token_stats = token_stats

    @property
    def name(self) -> str:
        return "vision"

    @property
    def description(self) -> str:
        return (
            "Analyze an image from a URL or local file path. "
            "Supports describing content, extracting text (OCR), "
            "and answering questions about images."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Image URL (https://...) or local file path to analyze",
                },
                "prompt": {
                    "type": "string",
                    "description": "Analysis instruction (default: describe the image)",
                },
            },
            "required": ["url"],
        }

    @staticmethod
    def _resolve_image_url(url: str) -> str:
        """Return an API-ready image URL. Local paths are base64-encoded."""
        if url.startswith(("http://", "https://")):
            return url
        path = url
        if path.startswith("file://"):
            path = path[7:]  # strip file:// (file:///foo → /foo)
        p = Path(path)
        if not p.is_file():
            raise FileNotFoundError(f"Local image not found: {path}")
        mime, _ = mimetypes.guess_type(path)
        if not mime or not mime.startswith("image/"):
            raise ValueError(f"Not an image file: {path} (mime={mime})")
        b64 = base64.b64encode(p.read_bytes()).decode()
        return f"data:{mime};base64,{b64}"

    async def execute(self, url: str, prompt: str | None = None, **kwargs: Any) -> str:
        prompt = prompt or "描述这张图片的内容。"

        try:
            image_url = self._resolve_image_url(url)
        except (FileNotFoundError, ValueError) as e:
            return f"Error: {e}"

        messages = [
            {
                "role": "user",
                "content": [
                    {"type": "image_url", "image_url": {"url": image_url}},
                    {"type": "text", "text": prompt},
                ],
            }
        ]

        try:
            response = await self._provider.chat(
                messages=messages,
                model=self._model,
                max_tokens=4096,
                temperature=0.3,
            )

            if response.usage and self._token_stats:
                model_name = self._model or self._provider.get_default_model()
                _effective_provider = (
                    model_name.split("/", 1)[0]
                    if "/" in model_name
                    else self._provider.provider_name
                )
                try:
                    self._token_stats.record(
                        model=model_name,
                        provider=_effective_provider,
                        usage=response.usage,
                        session_key="vision_tool",
                        user_message=prompt[:200],
                        output_content=response.content or "",
                        system_prompt="",
                        conversation_history="",
                        full_request_payload="",
                        finish_reason=response.finish_reason or "",
                        model_role="vision",
                    )
                except Exception as e:
                    logger.debug("Failed to record vision tool token stats: {}", e)
                logger.debug(
                    "👁️ VisionTool tokens: {} (prompt: {} + completion: {})",
                    response.usage.get("total_tokens", 0),
                    response.usage.get("prompt_tokens", 0),
                    response.usage.get("completion_tokens", 0),
                )

            return response.content or "No analysis result returned."
        except Exception as e:
            return f"Error analyzing image: {e}"
