"""LLM-facing site adapter tools (AVA-58, plan §F step 7)."""

from __future__ import annotations

import json
from typing import Any

from nanobot.agent.tools.base import Tool

from ava.tools.browser_substrate.adapter_registry import SiteAdapterRegistry
from ava.tools.browser_substrate.adapter_runner import AdapterRunner
from ava.tools.browser_substrate.client import BrowserSubstrateClient
from ava.tools.browser_substrate.fetch_tool import BrowserFetchTool


class SiteAdapterListTool(Tool):
    """Enumerate site adapters configured in the local registry."""

    def __init__(self, *, registry: SiteAdapterRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "site_adapter_list"

    @property
    def description(self) -> str:
        return (
            "List local site adapters (read-only manifests). v1 does not auto-"
            "fetch community adapters; if empty, see the returned hint."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {"type": "object", "properties": {}}

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **_: Any) -> str:  # type: ignore[override]
        manifests = [m.to_summary() for m in self._registry.list()]
        body: dict[str, Any] = {"adapters": manifests}
        if not manifests:
            body["hint"] = self._registry.empty_hint()
        if self._registry.errors:
            body["errors"] = list(self._registry.errors)
        return json.dumps(body)


class SiteAdapterInfoTool(Tool):
    """Return the full manifest (args_schema + steps) of one adapter."""

    def __init__(self, *, registry: SiteAdapterRegistry) -> None:
        self._registry = registry

    @property
    def name(self) -> str:
        return "site_adapter_info"

    @property
    def description(self) -> str:
        return "Return one adapter's args_schema, output_schema, and step list."

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Adapter id (from list)."},
            },
            "required": ["id"],
        }

    @property
    def read_only(self) -> bool:
        return True

    async def execute(self, **kwargs: Any) -> str:  # type: ignore[override]
        adapter_id = kwargs.get("id")
        if not isinstance(adapter_id, str) or not adapter_id:
            return json.dumps({"ok": False, "error": "`id` is required"})
        manifest = self._registry.get(adapter_id)
        if manifest is None:
            return json.dumps(
                {"ok": False, "error": f"adapter {adapter_id!r} not registered"}
            )
        return json.dumps({"ok": True, **manifest.to_info()})


class SiteAdapterRunTool(Tool):
    """Execute a registered adapter against the live browser context."""

    def __init__(
        self,
        *,
        registry: SiteAdapterRegistry,
        client: BrowserSubstrateClient,
        fetch_tool: BrowserFetchTool | None = None,
    ) -> None:
        self._registry = registry
        self._client = client
        self._fetch_tool = fetch_tool

    @property
    def name(self) -> str:
        return "site_adapter_run"

    @property
    def description(self) -> str:
        return (
            "Run a read-only site adapter. v1 only supports manifests with "
            "`read_only=true` from the configured local directory."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "id": {"type": "string", "description": "Adapter id from list."},
                "args": {
                    "type": "object",
                    "description": "Arguments matching the adapter's args_schema.",
                },
            },
            "required": ["id"],
        }

    async def execute(self, **kwargs: Any) -> str:  # type: ignore[override]
        adapter_id = kwargs.get("id")
        if not isinstance(adapter_id, str) or not adapter_id:
            return json.dumps({"ok": False, "error": "`id` is required"})
        manifest = self._registry.get(adapter_id)
        if manifest is None:
            return json.dumps(
                {"ok": False, "error": f"adapter {adapter_id!r} not registered"}
            )
        runner = AdapterRunner(
            manifest=manifest, client=self._client, fetch_tool=self._fetch_tool
        )
        result = await runner.run(kwargs.get("args") or {})
        return json.dumps(
            {
                "ok": result.ok,
                "id": adapter_id,
                "output": result.output,
                "steps": result.steps,
                **({"error": result.error} if result.error else {}),
            }
        )
