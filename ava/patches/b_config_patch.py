"""Monkey patch to extend nanobot config schema with ava fields.

Adds to AgentDefaults:
  - claude_code_model: str  — model for ClaudeCodeTool
  - claude_code_config: dict | None  — extra config (api_key, base_url)
  - vision_model: str | None  — override model for VisionTool
  - mini_model: str | None   — lightweight model for quick tasks

Note: voice_model was removed — voice transcription uses upstream Groq Whisper.
"""

from __future__ import annotations

from loguru import logger

from ava.launcher import register_patch


def apply_config_patch() -> str:
    import sys
    # If schema fork was applied, AgentDefaults already has the new fields — skip
    if getattr(sys.modules.get("nanobot.config.schema"), "_ava_fork", False):
        return "schema fork active — config_patch skipped"

    from nanobot.config import schema as schema_mod

    AgentDefaults = schema_mod.AgentDefaults

    # Add fields only if not already present (idempotent)
    _defaults = {
        "claude_code_model": "claude-sonnet-4-20250514",
        "claude_code_config": None,
        "vision_model": None,
        "mini_model": None,
        # voice_model removed — voice transcription uses upstream Groq Whisper
    }

    added = []
    for field_name, default_val in _defaults.items():
        if not hasattr(AgentDefaults, field_name):
            # Pydantic v2: inject via __annotations__ + __fields__
            try:
                from pydantic.fields import FieldInfo
                AgentDefaults.model_fields[field_name] = FieldInfo(default=default_val)
                AgentDefaults.__annotations__[field_name] = type(default_val) if default_val is not None else "Any"
                added.append(field_name)
            except Exception as exc:
                logger.warning("Failed to add field {} to AgentDefaults: {}", field_name, exc)

    if added:
        # Rebuild model so new fields are recognized
        try:
            AgentDefaults.model_rebuild(force=True)
        except Exception as exc:
            logger.warning("model_rebuild failed (non-critical): {}", exc)

    return f"AgentDefaults extended with: {added or 'already present'}"


register_patch("config_schema", apply_config_patch)
