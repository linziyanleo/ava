"""Image generation and editing tool with provider-aware routing."""

import asyncio
import base64
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

_ZENMUX_VERTEX_BASE_URL = "https://zenmux.ai/api/vertex-ai"


def _load_image_gen_config() -> tuple[str, str, str, str]:
    """Load image generation model, provider, api_key, api_base from config.json."""
    from nanobot.config.loader import load_config

    config = load_config()
    model = config.agents.defaults.image_gen_model
    if not model:
        raise ValueError("imageGenModel is not configured in config.json")
    p = config.get_provider(model)
    if not p or not p.api_key:
        raise ValueError(f"No provider/api_key found for imageGenModel '{model}'")
    provider_name = ""
    if hasattr(config, "get_provider_name"):
        provider_name = config.get_provider_name(model) or ""
    api_base = config.get_api_base(model) or p.api_base or ""
    return model, provider_name, p.api_key, api_base


def _model_prefix(model: str) -> str:
    return model.lower().split("/", 1)[0] if "/" in model else ""


def _effective_provider_name(model: str, provider_name: str, api_base: str) -> str:
    if "zenmux.ai" in api_base.lower():
        return "zenmux"
    return provider_name or _model_prefix(model)


def _normalize_genai_base(api_base: str, provider_name: str) -> str:
    base_url = api_base.rstrip("/")
    if provider_name == "zenmux":
        if not base_url or "zenmux.ai" in base_url.lower() and "/vertex-ai" not in base_url:
            return _ZENMUX_VERTEX_BASE_URL
    if base_url.endswith("/v1"):
        return base_url[:-3]
    return base_url


def _request_model_for_genai(model: str, provider_name: str) -> str:
    if provider_name == "zenmux" and model.startswith("zenmux/"):
        return model.split("/", 1)[1]
    return model


def _request_model_for_openai(model: str) -> str:
    if model.startswith("openai/"):
        return model.split("/", 1)[1]
    return model


def _is_google_image_model(model: str) -> bool:
    normalized = model.lower()
    return normalized.startswith("google/") or normalized.startswith("gemini-")


def _mime_type_for_path(path: Path) -> str:
    suffix = path.suffix.lower()
    mime_map = {
        ".png": "image/png",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
        ".webp": "image/webp",
        ".avif": "image/avif",
        ".gif": "image/gif",
    }
    return mime_map.get(suffix, "image/png")


def _prompt_requests_transparent_background(prompt: str) -> bool:
    normalized = prompt.lower()
    return "transparent" in normalized or "透明" in prompt


class ImageGenTool(Tool):
    """Generate or edit images using the configured image provider."""

    def __init__(
        self,
        token_stats: Any | None = None,
        media_service: Any | None = None,
        task_store: Any | None = None,
        timeout: int = 300,
        background: bool = True,
        auto_continue: bool = False,
        auto_send: bool = True,
    ) -> None:
        model, provider_name, api_key, api_base = _load_image_gen_config()
        self._api_key = api_key
        self._api_base = api_base
        self._model = model
        self._provider_name = _effective_provider_name(model, provider_name, api_base)
        self._token_stats = token_stats
        self._media_service = media_service
        self._task_store = task_store
        self._timeout = timeout
        self._background = background
        self._auto_continue = auto_continue
        self._auto_send = auto_send
        self._client = None
        self._generated_dir = _get_generated_dir()
        self._records_file = _get_records_file()
        self._generated_dir.mkdir(parents=True, exist_ok=True)
        self._channel = "cli"
        self._chat_id = "direct"
        self._session_key = "cli:direct"

    def set_context(
        self, channel: str, chat_id: str, *, session_key: str | None = None,
    ) -> None:
        self._channel = channel
        self._chat_id = chat_id
        self._session_key = session_key or f"{channel}:{chat_id}"

    @property
    def name(self) -> str:
        return "image_gen"

    @property
    def description(self) -> str:
        return (
            "Generate or edit images using AI. "
            "For generation: provide a text prompt describing the desired image. "
            "For editing: provide a reference_image path and an edit instruction as prompt. "
            "By default this runs as a background task and the generated image is sent to the current channel when complete. "
            "Set continue_after_completion=true only when you need the agent to continue a multi-step workflow after generation."
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
                "continue_after_completion": {
                    "type": "boolean",
                    "description": (
                        "Optional: trigger agent continuation after the background image task completes. "
                        "Default is false because generated images are sent automatically."
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

        base_url = _normalize_genai_base(self._api_base, self._provider_name)
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

    def _get_openai_client(self):
        """Lazily create the OpenAI-compatible client."""
        if self._client is not None:
            return self._client

        from openai import OpenAI

        kwargs: dict[str, Any] = {"api_key": self._api_key}
        if self._api_base:
            kwargs["base_url"] = self._api_base.rstrip("/")
        self._client = OpenAI(**kwargs)
        return self._client

    def _save_image(self, image, record_id: str, index: int) -> Path:
        """Save a PIL/google.genai Image to the generated directory."""
        filename = f"{record_id}_{index}.png"
        path = self._generated_dir / filename
        if hasattr(image, "save"):
            image.save(str(path))
            return path
        image_bytes = getattr(image, "image_bytes", None) or getattr(image, "imageBytes", None)
        if image_bytes:
            path.write_bytes(image_bytes)
            return path
        raise ValueError("Unsupported image object returned by image generation model")

    def _save_image_bytes(self, image_bytes: bytes, record_id: str, index: int) -> Path:
        filename = f"{record_id}_{index}.png"
        path = self._generated_dir / filename
        path.write_bytes(image_bytes)
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
        continue_after_completion: bool | None = None,
        **kwargs: Any,
    ) -> str:
        ref_error = self._validate_reference_image(reference_image)
        if ref_error:
            return ref_error

        if self._background and self._task_store:
            auto_continue = (
                self._auto_continue
                if continue_after_completion is None
                else bool(continue_after_completion)
            )
            submit = self._task_store.submit_task(
                executor=self._execute_background,
                origin_session_key=self._session_key,
                prompt=prompt,
                project_path=str(self._generated_dir),
                timeout=self._timeout,
                auto_continue=auto_continue,
                task_type="image_gen",
                workspace_exclusive=False,
                reference_image=reference_image,
                auto_send=self._auto_send,
            )
            return self._format_submit_result(submit)

        try:
            return await asyncio.wait_for(
                self._execute_generation(prompt, reference_image),
                timeout=self._timeout,
            )
        except asyncio.TimeoutError:
            return f"Error generating image: Timed out after {self._timeout}s"

    def _validate_reference_image(self, reference_image: str | None) -> str:
        if reference_image and not Path(reference_image).is_file():
            return f"Error: Reference image not found: {reference_image}"
        return ""

    @staticmethod
    def _format_submit_result(result: Any) -> str:
        return (
            f"Image generation task started (id: {result.task_id}). "
            "Use /task or /bg-tasks to check progress."
        )

    @staticmethod
    def _extract_generated_image_paths(result_text: str) -> list[str]:
        marker = "Generated image(s):"
        for line in result_text.splitlines():
            if line.startswith(marker):
                return [
                    item.strip()
                    for item in line[len(marker):].split(",")
                    if item.strip()
                ]
        return []

    async def _execute_background(
        self,
        *,
        prompt: str = "",
        reference_image: str | None = None,
        auto_send: bool = True,
        **_kw: Any,
    ) -> dict[str, Any]:
        result_text = await self._execute_generation(prompt, reference_image)
        if result_text.startswith("Error"):
            raise RuntimeError(result_text)
        media = self._extract_generated_image_paths(result_text) if auto_send else []
        return {"result": result_text, "media": media}

    async def _execute_generation(
        self,
        prompt: str,
        reference_image: str | None = None,
    ) -> str:
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
            ref_path: Path | None = None
            if reference_image:
                ref_path = Path(reference_image)
                if not ref_path.is_file():
                    record["status"] = "error"
                    record["error"] = f"Reference image not found: {reference_image}"
                    self._write_record(record)
                    return f"Error: Reference image not found: {reference_image}"
            image_paths: list[str] = []
            text_parts: list[str] = []
            usage_metadata = None

            request_model = _request_model_for_genai(self._model, self._provider_name)
            if self._provider_name == "openai":
                image_paths = await self._execute_openai_images(prompt, ref_path, record_id)
            elif _is_google_image_model(request_model):
                text_parts, image_paths, usage_metadata = await self._execute_generate_content(
                    prompt,
                    ref_path,
                    record_id,
                )
            else:
                image_paths = await self._execute_generate_images(prompt, ref_path, record_id)

            record["output_images"] = image_paths
            record["output_text"] = "\n".join(text_parts)

            if not image_paths and not text_parts:
                record["status"] = "error"
                record["error"] = "No output received from model"
                self._write_record(record)
                return "Error: No output received from the image generation model."

            if self._token_stats and usage_metadata:
                um = usage_metadata
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
                        provider=self._provider_name,
                        usage=usage,
                        session_key=self._session_key,
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

    async def _execute_generate_content(
        self,
        prompt: str,
        ref_path: Path | None,
        record_id: str,
    ) -> tuple[list[str], list[str], Any | None]:
        import asyncio

        from google.genai import types

        client = self._get_client()

        contents: list[Any] = []
        if ref_path:
            image_part = types.Part.from_bytes(
                data=ref_path.read_bytes(),
                mime_type=_mime_type_for_path(ref_path),
            )
            contents.append(image_part)
        contents.append(prompt)

        response = await asyncio.to_thread(
            client.models.generate_content,
            model=_request_model_for_genai(self._model, self._provider_name),
            contents=contents,
            config=types.GenerateContentConfig(response_modalities=["TEXT", "IMAGE"]),
        )

        text_parts: list[str] = []
        image_paths: list[str] = []
        for i, part in enumerate(getattr(response, "parts", None) or []):
            if getattr(part, "text", None) is not None:
                text_parts.append(part.text)
            elif getattr(part, "inline_data", None) is not None:
                image = part.as_image()
                saved_path = self._save_image(image, record_id, i)
                image_paths.append(str(saved_path))
                logger.info("Image saved: {}", saved_path)

        return text_parts, image_paths, getattr(response, "usage_metadata", None)

    async def _execute_generate_images(
        self,
        prompt: str,
        ref_path: Path | None,
        record_id: str,
    ) -> list[str]:
        import asyncio

        from google.genai import types

        client = self._get_client()
        config = types.GenerateImagesConfig(
            number_of_images=1,
            output_mime_type="image/png",
        )

        if ref_path:
            reference_image = types.Image(
                image_bytes=ref_path.read_bytes(),
                mime_type=_mime_type_for_path(ref_path),
            )
            response = await asyncio.to_thread(
                client.models.edit_image,
                model=_request_model_for_genai(self._model, self._provider_name),
                prompt=prompt,
                reference_images=[
                    types.RawReferenceImage(
                        reference_id=1,
                        reference_image=reference_image,
                    )
                ],
                config=types.EditImageConfig(
                    number_of_images=1,
                    output_mime_type="image/png",
                ),
            )
        else:
            response = await asyncio.to_thread(
                client.models.generate_images,
                model=_request_model_for_genai(self._model, self._provider_name),
                prompt=prompt,
                config=config,
            )

        image_paths: list[str] = []
        for i, generated in enumerate(getattr(response, "generated_images", None) or []):
            image = getattr(generated, "image", None)
            if image is None:
                continue
            saved_path = self._save_image(image, record_id, i)
            image_paths.append(str(saved_path))
            logger.info("Image saved: {}", saved_path)
        return image_paths

    async def _execute_openai_images(
        self,
        prompt: str,
        ref_path: Path | None,
        record_id: str,
    ) -> list[str]:
        import asyncio

        client = self._get_openai_client()
        model = _request_model_for_openai(self._model)
        base_kwargs: dict[str, Any] = {
            "model": model,
            "prompt": prompt,
            "n": 1,
            "response_format": "b64_json",
            "output_format": "png",
        }
        if _prompt_requests_transparent_background(prompt):
            base_kwargs["background"] = "transparent"

        if ref_path:
            with ref_path.open("rb") as image_file:
                response = await asyncio.to_thread(
                    client.images.edit,
                    image=image_file,
                    **base_kwargs,
                )
        else:
            response = await asyncio.to_thread(
                client.images.generate,
                **base_kwargs,
            )

        image_paths: list[str] = []
        for i, item in enumerate(getattr(response, "data", None) or []):
            b64_json = getattr(item, "b64_json", None)
            if not b64_json:
                continue
            saved_path = self._save_image_bytes(base64.b64decode(b64_json), record_id, i)
            image_paths.append(str(saved_path))
            logger.info("Image saved: {}", saved_path)
        return image_paths
