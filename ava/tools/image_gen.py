"""Image generation and editing tool using Google GenAI SDK."""

import json
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

from loguru import logger

from nanobot.agent.tools.base import Tool
from ava.runtime import paths as runtime_paths


def _get_generated_dir() -> Path:
    return runtime_paths.get_generated_media_dir()


def _get_records_file() -> Path:
    return _get_generated_dir() / "records.jsonl"

def _load_image_gen_config() -> tuple[str, str, str]:
    """Load image generation model, api_key, api_base from config.json."""
    from nanobot.config.loader import load_config

    config = load_config()
    model = config.agents.defaults.image_gen_model
    if not model:
        raise ValueError("imageGenModel is not configured in config.json")
    p = config.get_provider(model)
    if not p or not p.api_key:
        raise ValueError(f"No provider/api_key found for imageGenModel '{model}'")
    api_base = config.get_api_base(model) or p.api_base or ""
    return model, p.api_key, api_base

class ImageGenTool(Tool):
    """Generate or edit images using Gemini's native image generation capabilities."""

    def __init__(
        self,
        token_stats: Any | None = None,
        media_service: Any | None = None,
    ) -> None:
        model, api_key, api_base = _load_image_gen_config()
        self._api_key = api_key
        self._api_base = api_base
        self._model = model
        self._token_stats = token_stats
        self._media_service = media_service
        self._client = None
        self._generated_dir = _get_generated_dir()
        self._records_file = _get_records_file()
        self._generated_dir.mkdir(parents=True, exist_ok=True)

    @property
    def name(self) -> str:
        return "image_gen"

    @property
    def description(self) -> str:
        return (
            "Generate or edit images using AI. "
            "For generation: provide a text prompt describing the desired image. "
            "For editing: provide a reference_image path and an edit instruction as prompt. "
            "Returns the file path(s) of generated images which can be sent via the message tool."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "prompt": {
                    "type": "string",
                    "description": (
                        "Text prompt describing the image to generate, "
                        "or edit instruction when reference_image is provided"
                    ),
                },
                "reference_image": {
                    "type": "string",
                    "description": (
                        "Optional: file path to a reference image for editing. "
                        "When provided, the prompt is treated as an edit instruction."
                    ),
                },
            },
            "required": ["prompt"],
        }

    def _get_client(self):
        """Lazily create the GenAI client."""
        if self._client is not None:
            return self._client

        from google import genai
        from google.genai import types

        base_url = self._api_base.rstrip("/")
        if base_url.endswith("/v1"):
            base_url = base_url[:-3]
            api_version = "v1"
        else:
            api_version = "v1"

        self._client = genai.Client(
            api_key=self._api_key,
            vertexai=True,
            http_options=types.HttpOptions(
                api_version=api_version,
                base_url=base_url,
            ),
        )
        return self._client

    def _save_image(self, image, record_id: str, index: int) -> Path:
        """Save a PIL Image to the generated directory."""
        filename = f"{record_id}_{index}.png"
        path = self._generated_dir / filename
        image.save(str(path))
        return path

    def _write_record(self, record: dict) -> None:
        """Write a generation record via MediaService (DB) or legacy JSONL fallback."""
        if self._media_service:
            try:
                self._media_service.write_record(record)
            except Exception as e:
                logger.warning("Failed to write image gen record via DB: {}", e)
            return
        try:
            with open(self._records_file, "a", encoding="utf-8") as f:
                f.write(json.dumps(record, ensure_ascii=False) + "\n")
        except Exception as e:
            logger.warning("Failed to write image gen record: {}", e)

    async def execute(
        self,
        prompt: str,
        reference_image: str | None = None,
        **kwargs: Any,
    ) -> str:
        import asyncio

        record_id = uuid.uuid4().hex[:12]
        record = {
            "id": record_id,
            "timestamp": datetime.now(timezone.utc).isoformat(),
            "prompt": prompt,
            "reference_image": reference_image,
            "output_images": [],
            "output_text": "",
            "model": self._model,
            "status": "success",
            "error": None,
        }

        try:
            from google.genai import types

            client = self._get_client()

            contents: list[Any] = []
            if reference_image:
                ref_path = Path(reference_image)
                if not ref_path.is_file():
                    record["status"] = "error"
                    record["error"] = f"Reference image not found: {reference_image}"
                    self._write_record(record)
                    return f"Error: Reference image not found: {reference_image}"

                # Determine MIME type from extension
                suffix = ref_path.suffix.lower()
                mime_map = {
                    ".png": "image/png",
                    ".jpg": "image/jpeg",
                    ".jpeg": "image/jpeg",
                    ".webp": "image/webp",
                    ".avif": "image/avif",
                    ".gif": "image/gif",
                }
                mime_type = mime_map.get(suffix, "image/png")
                image_bytes = ref_path.read_bytes()
                image_part = types.Part.from_bytes(
                    data=image_bytes, mime_type=mime_type
                )
                contents.append(image_part)

            contents.append(prompt)

            config = types.GenerateContentConfig(
                response_modalities=["TEXT", "IMAGE"],
            )

            response = await asyncio.to_thread(
                client.models.generate_content,
                model=self._model,
                contents=contents,
                config=config,
            )

            text_parts: list[str] = []
            image_paths: list[str] = []

            if response.parts:
                image_saved = False
                for i, part in enumerate(response.parts):
                    if part.text is not None:
                        text_parts.append(part.text)
                    elif part.inline_data is not None and not image_saved:
                        image = part.as_image()
                        saved_path = self._save_image(image, record_id, i)
                        image_paths.append(str(saved_path))
                        image_saved = True
                        logger.info("Image saved: {}", saved_path)

            record["output_images"] = image_paths
            record["output_text"] = "\n".join(text_parts)

            if not image_paths and not text_parts:
                record["status"] = "error"
                record["error"] = "No output received from model"
                self._write_record(record)
                return "Error: No output received from the image generation model."

            if self._token_stats and hasattr(response, "usage_metadata") and response.usage_metadata:
                um = response.usage_metadata
                # Google GenAI 使用不同的缓存字段名
                cached_tokens = getattr(um, "cached_content_token_count", 0) or 0
                usage = {
                    "prompt_tokens": getattr(um, "prompt_token_count", 0) or 0,
                    "completion_tokens": getattr(um, "candidates_token_count", 0) or 0,
                    "total_tokens": getattr(um, "total_token_count", 0) or 0,
                    "prompt_tokens_details": {"cached_tokens": cached_tokens} if cached_tokens else None,
                }
                # 构建输出内容，包含生成的图片路径
                output_content = "\n".join(text_parts) if text_parts else ""
                if image_paths:
                    output_content += ("\n" if output_content else "") + f"Generated: {', '.join(image_paths)}"
                try:
                    self._token_stats.record(
                        model=self._model,
                        provider="google",
                        usage=usage,
                        session_key="image_gen",
                        turn_seq=0,
                        user_message=prompt[:500],
                        output_content=output_content,
                        finish_reason="stop",
                        model_role="imageGen",
                    )
                except Exception as e:
                    logger.debug("Failed to record image gen token stats: {}", e)

            self._write_record(record)

            result_parts: list[str] = []
            if image_paths:
                paths_str = ", ".join(image_paths)
                result_parts.append(f"Generated image(s): {paths_str}")
            if text_parts:
                result_parts.append("\n".join(text_parts))

            return "\n".join(result_parts)

        except ModuleNotFoundError as e:
            error_msg = f"Missing image generation dependency: {e}"
            record["status"] = "error"
            record["error"] = error_msg
            self._write_record(record)
            logger.error("Image generation failed: {}", error_msg)
            return f"Error generating image: {error_msg}"
        except Exception as e:
            error_msg = str(e)
            record["status"] = "error"
            record["error"] = error_msg
            self._write_record(record)
            logger.error("Image generation failed: {}", error_msg)
            return f"Error generating image: {error_msg}"
