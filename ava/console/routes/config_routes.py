"""Config management routes."""

from __future__ import annotations

import json
import tomllib
from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Request

from ava.console import auth
from ava.console.models import ConfigUpdateRequest, RevealRequest, UserInfo
from ava.console.middleware import get_client_ip


def _parse_config_body(filename: str, content: str) -> tuple[Any, str | None]:
    """Parse string body into a dict matching the file's serialization.

    Returns ``(parsed_or_None, parse_error_or_None)``.
    """
    lower = filename.lower()
    if lower.endswith(".toml"):
        try:
            return tomllib.loads(content), None
        except tomllib.TOMLDecodeError as exc:
            return None, f"TOML parse error: {exc}"
    if lower.endswith(".json"):
        if not content.strip():
            return {}, None
        try:
            return json.loads(content), None
        except json.JSONDecodeError as exc:
            return None, f"JSON parse error: {exc}"
    return None, "unsupported config format"


def _validate_config_body(filename: str, content: str, schema: dict) -> list[dict[str, str]]:
    """Validate ``content`` against ``schema`` and return error rows.

    Each row is ``{"path": "/a/b", "message": "..."}``. Empty list = valid.
    """
    parsed, parse_error = _parse_config_body(filename, content)
    if parse_error is not None:
        return [{"path": "/", "message": parse_error}]
    import jsonschema  # local import — keeps the module importable in tests
    from jsonschema.protocols import Validator

    validator_cls: type[Validator] = jsonschema.Draft202012Validator
    validator = validator_cls(schema)
    rows: list[dict[str, str]] = []
    for err in validator.iter_errors(parsed):
        path = "/" + "/".join(str(p) for p in err.absolute_path) if err.absolute_path else "/"
        rows.append({"path": path, "message": err.message})
    return rows

router = APIRouter(prefix="/api/config", tags=["config"])


# AVA-26 §F1/F2: filename → AgentAdapter that owns the JSON Schema for the
# corresponding raw config file. Adapters expose the schema via
# `get_config_schema()` (already implemented for all four adapters).
_FILENAME_TO_ADAPTER: dict[str, str] = {
    "codex-config.toml": "codex",
    "claude-code-settings.json": "claude_code",
    "image-gen-config.json": "image_gen",
    "config.json": "nanobot",
    "nanobot-config.json": "nanobot",
}


def _resolve_adapter_schema(filename: str) -> dict | None:
    adapter_name = _FILENAME_TO_ADAPTER.get(filename)
    if adapter_name is None:
        return None
    if adapter_name == "codex":
        from ava.agents.codex.adapter import CodexAdapter

        return CodexAdapter().get_config_schema()
    if adapter_name == "claude_code":
        from ava.agents.claude_code.adapter import ClaudeCodeAdapter

        return ClaudeCodeAdapter().get_config_schema()
    if adapter_name == "image_gen":
        from ava.agents.image_gen.adapter import ImageGenAdapter

        return ImageGenAdapter().get_config_schema()
    if adapter_name == "nanobot":
        from ava.agents.nanobot.adapter import NanobotAdapter

        return NanobotAdapter().get_config_schema()
    return None


@router.get("/list")
async def list_configs(user: UserInfo = Depends(auth.require_role(*auth.READ_ROLES))):
    from ava.console.app import get_services_for_user
    return get_services_for_user(user).config.list_configs()


@router.get("/{name:path}/schema")
async def read_config_schema(
    name: str,
    user: UserInfo = Depends(auth.require_role(*auth.READ_ROLES)),
):
    """AVA-26 §F2: return the JSON Schema describing the editable config file.

    Returns 404 when no adapter owns the schema (e.g. cron/jobs.json). UI is
    expected to fall back to the Raw editor in that case.
    """
    schema = _resolve_adapter_schema(name)
    if schema is None:
        raise HTTPException(
            status_code=404,
            detail={"code": "schema_unavailable", "filename": name},
        )
    return {"filename": name, "schema": schema}


@router.get("/{name:path}")
async def read_config(
    name: str,
    user: UserInfo = Depends(auth.require_role(*auth.READ_ROLES)),
):
    from ava.console.app import get_services_for_user

    try:
        return get_services_for_user(user).config.read_config(name, mask=False)
    except (ValueError, FileNotFoundError) as e:
        raise HTTPException(status_code=404, detail=str(e))


@router.put("/{name:path}")
async def update_config(
    name: str,
    body: ConfigUpdateRequest,
    request: Request,
    user: UserInfo = Depends(auth.require_role("owner")),
):
    from ava.console.app import get_services_for_user

    # AVA-26 §F3: jsonschema validation before write. 422 + field-path errors.
    schema = _resolve_adapter_schema(name)
    if schema is not None:
        errors = _validate_config_body(name, body.content, schema)
        if errors:
            raise HTTPException(
                status_code=422,
                detail={"code": "config_invalid", "errors": errors},
            )

    svc = get_services_for_user(user)
    try:
        result = svc.config.update_config(name, body.content, body.mtime)
    except ValueError as e:
        raise HTTPException(status_code=409, detail=str(e))

    svc.audit.log(
        user=user.username, role=user.role, action="config.update",
        target=name, ip=get_client_ip(request),
    )
    return result


@router.post("/{name:path}/reveal")
async def reveal_secret(
    name: str,
    body: RevealRequest,
    request: Request,
    user: UserInfo = Depends(auth.require_role("owner")),
):
    from ava.console.app import get_services

    svc = get_services()
    value = svc.config.reveal_secret(name, body.field_path)
    if value is None:
        raise HTTPException(status_code=404, detail="Field not found")

    svc.audit.log(
        user=user.username, role=user.role, action="secret.reveal",
        target=name, detail={"field_path": body.field_path},
        ip=get_client_ip(request),
    )
    return {"value": value}
