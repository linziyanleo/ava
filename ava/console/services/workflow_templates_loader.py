"""Built-in workflow template loader (AVA-48 plan-step-7).

Templates are static JSON resources living next to this module under
``workflow_templates/``. Each file is a complete v1 ``definition`` document
that ``validate_definition`` accepts. The loader is read-only — templates can
be added by dropping a new ``.json`` file in the directory; nothing else needs
to change.
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from ava.console.services.workflow_definition_schema import validate_definition


_TEMPLATES_DIR = Path(__file__).parent / "workflow_templates"


def _read_template(path: Path) -> dict[str, Any]:
    raw = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise ValueError(f"template {path.name} is not a JSON object")
    if "definition" not in raw or not isinstance(raw["definition"], dict):
        raise ValueError(f"template {path.name} missing 'definition' object")
    # double-check the embedded definition is v1 valid; if not, surface clearly.
    validate_definition(raw["definition"])
    raw.setdefault("id", path.stem)
    raw.setdefault("name", raw.get("id"))
    raw.setdefault("description", "")
    return raw


def list_templates() -> list[dict[str, Any]]:
    """Return all templates as ``[{id, name, description, definition}]``."""
    if not _TEMPLATES_DIR.is_dir():
        return []
    out: list[dict[str, Any]] = []
    for path in sorted(_TEMPLATES_DIR.glob("*.json")):
        try:
            out.append(_read_template(path))
        except (ValueError, json.JSONDecodeError) as exc:
            # Drop bad templates from the list rather than blow up the API; bad
            # templates are an authoring bug surfaced via tests, not user input.
            from loguru import logger

            logger.warning("workflow template {} failed to load: {}", path.name, exc)
    return out


def get_template(template_id: str) -> dict[str, Any] | None:
    for tpl in list_templates():
        if tpl["id"] == template_id:
            return tpl
    return None
