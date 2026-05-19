"""Adapter step interpreter (AVA-58, plan §F step 7).

Executes a :class:`SiteAdapterManifest` against a
:class:`BrowserSubstrateClient`. Only the approved step kinds are honored:

* ``set_var``                — assign a literal to a named variable.
* ``browser_fetch``          — call the substrate fetch tool.
* ``browser_snapshot``       — call ``mcp_{server}_browser_snapshot`` (no JS).
* ``browser_evaluate_readonly`` — call ``mcp_{server}_browser_evaluate`` with
  a fixed read-only helper from a whitelist (no caller JS string).
* ``extract_jsonpath``       — pull a value from a previous step's JSON output
  using a tiny dotted-path subset (``$.a.b[0]``).

No step accepts an arbitrary JS string. Cross-step state lives in a single
dict; placeholders inside step params use ``{{var}}`` substitution.
"""

from __future__ import annotations

import json
import re
from dataclasses import dataclass
from typing import Any, Mapping

from ava.tools.browser_substrate.adapter_registry import (
    SiteAdapterManifest,
    SiteAdapterStep,
    _APPROVED_EVAL_HELPERS,
)
from ava.tools.browser_substrate.client import BrowserSubstrateClient
from ava.tools.browser_substrate.fetch_tool import BrowserFetchTool


_PLACEHOLDER_RE = re.compile(r"\{\{\s*([A-Za-z_][A-Za-z0-9_]*)\s*\}\}")


class AdapterStepFailed(RuntimeError):
    """Raised when a step rejects its inputs or produces an error response."""


@dataclass
class AdapterRunResult:
    ok: bool
    output: dict[str, Any]
    steps: list[dict[str, Any]]
    error: str | None = None


def _substitute(value: Any, vars_: Mapping[str, Any]) -> Any:
    if isinstance(value, str):
        def _lookup(m: re.Match[str]) -> str:
            key = m.group(1)
            if key not in vars_:
                raise AdapterStepFailed(f"unknown variable {{{{ {key} }}}}")
            return str(vars_[key])

        return _PLACEHOLDER_RE.sub(_lookup, value)
    if isinstance(value, list):
        return [_substitute(v, vars_) for v in value]
    if isinstance(value, dict):
        return {k: _substitute(v, vars_) for k, v in value.items()}
    return value


def _resolve_jsonpath(data: Any, path: str) -> Any:
    """Tiny dotted/bracket subset: '$', '$.a.b', '$.a[0].b'."""
    if not path or path == "$":
        return data
    if not path.startswith("$"):
        raise AdapterStepFailed(f"jsonpath must start with '$': {path!r}")
    cursor: Any = data
    tokens = re.findall(r"\.([A-Za-z_][A-Za-z0-9_]*)|\[(\d+)\]", path[1:])
    for name, idx in tokens:
        if name:
            if not isinstance(cursor, dict) or name not in cursor:
                raise AdapterStepFailed(f"jsonpath miss: {path!r} at {name!r}")
            cursor = cursor[name]
        else:
            i = int(idx)
            if not isinstance(cursor, list) or i >= len(cursor):
                raise AdapterStepFailed(f"jsonpath miss: {path!r} at [{idx}]")
            cursor = cursor[i]
    return cursor


class AdapterRunner:
    """Stateful one-shot interpreter for a manifest invocation."""

    def __init__(
        self,
        *,
        manifest: SiteAdapterManifest,
        client: BrowserSubstrateClient,
        fetch_tool: BrowserFetchTool | None = None,
    ) -> None:
        self._manifest = manifest
        self._client = client
        self._fetch_tool = fetch_tool or BrowserFetchTool(client=client)

    async def run(self, args: Mapping[str, Any] | None = None) -> AdapterRunResult:
        vars_: dict[str, Any] = {**(args or {})}
        steps_log: list[dict[str, Any]] = []
        last_result: Any = None

        try:
            for idx, step in enumerate(self._manifest.steps):
                outcome = await self._run_step(step, vars_, last_result)
                last_result = outcome.get("value", last_result)
                steps_log.append(
                    {"index": idx, "kind": step.kind, "ok": True, **outcome.get("log", {})}
                )
        except AdapterStepFailed as exc:
            steps_log.append(
                {"index": len(steps_log), "ok": False, "error": str(exc)}
            )
            return AdapterRunResult(ok=False, output={}, steps=steps_log, error=str(exc))

        output = {k: v for k, v in vars_.items() if k.startswith("out_")}
        if not output and last_result is not None:
            output = {"out_last": last_result}
        return AdapterRunResult(ok=True, output=output, steps=steps_log)

    async def _run_step(
        self,
        step: SiteAdapterStep,
        vars_: dict[str, Any],
        last_result: Any,
    ) -> dict[str, Any]:
        params = _substitute(step.params, vars_)
        if step.kind == "set_var":
            name = params.get("name")
            if not isinstance(name, str) or not name:
                raise AdapterStepFailed("set_var requires a string `name`")
            vars_[name] = params.get("value")
            return {"value": vars_[name], "log": {"name": name}}

        if step.kind == "browser_fetch":
            url = params.get("url")
            if not isinstance(url, str) or not url:
                raise AdapterStepFailed("browser_fetch step requires a string `url`")
            raw = await self._fetch_tool.execute(
                url=url,
                method=params.get("method", "GET"),
                headers=params.get("headers") or {},
                with_body=bool(params.get("with_body", True)),
                allowed_origins=params.get("allowed_origins"),
            )
            try:
                payload = json.loads(raw)
            except json.JSONDecodeError as exc:
                raise AdapterStepFailed(
                    f"browser_fetch returned non-JSON: {exc}"
                ) from exc
            if not payload.get("ok"):
                raise AdapterStepFailed(
                    f"browser_fetch failed: {payload.get('error', 'unknown')}"
                )
            output_var = params.get("output_var")
            if isinstance(output_var, str) and output_var:
                vars_[output_var] = payload
            return {"value": payload, "log": {"url": url, "status": payload.get("status")}}

        if step.kind == "browser_snapshot":
            raw = await self._client.call_mcp("browser_snapshot", {})
            output_var = params.get("output_var")
            if isinstance(output_var, str) and output_var:
                vars_[output_var] = raw
            return {"value": raw, "log": {"chars": len(raw)}}

        if step.kind == "browser_evaluate_readonly":
            helper = params.get("helper")
            if helper not in _APPROVED_EVAL_HELPERS:
                raise AdapterStepFailed(
                    f"browser_evaluate_readonly helper {helper!r} not in whitelist"
                )
            selector = params.get("selector")
            if not isinstance(selector, str) or not selector:
                raise AdapterStepFailed("browser_evaluate_readonly requires `selector`")
            attribute = params.get("attribute")
            fn = _build_readonly_helper_fn(
                helper=helper, selector=selector, attribute=attribute
            )
            raw = await self._client.call_mcp("browser_evaluate", {"function": fn})
            output_var = params.get("output_var")
            if isinstance(output_var, str) and output_var:
                vars_[output_var] = raw
            return {"value": raw, "log": {"helper": helper}}

        if step.kind == "extract_jsonpath":
            path = params.get("path", "$")
            output_var = params.get("output_var")
            source = last_result
            if "from" in params:
                source_var = params["from"]
                if source_var not in vars_:
                    raise AdapterStepFailed(f"extract_jsonpath unknown source var {source_var!r}")
                source = vars_[source_var]
            value = _resolve_jsonpath(source, str(path))
            if isinstance(output_var, str) and output_var:
                vars_[output_var] = value
            return {"value": value, "log": {"path": path}}

        raise AdapterStepFailed(f"unknown step kind {step.kind!r} (registry should reject earlier)")


def _build_readonly_helper_fn(
    *,
    helper: str,
    selector: str,
    attribute: str | None,
) -> str:
    """Build the constant JS for an approved read-only DOM helper."""
    sel = json.dumps(selector)
    attr = json.dumps(attribute or "")
    if helper == "text_content":
        return f"() => {{ const el = document.querySelector({sel}); return el ? el.textContent : null; }}"
    if helper == "inner_text":
        return f"() => {{ const el = document.querySelector({sel}); return el ? el.innerText : null; }}"
    if helper == "attribute":
        return (
            f"() => {{ const el = document.querySelector({sel}); "
            f"return el ? el.getAttribute({attr}) : null; }}"
        )
    if helper == "query_selector_all":
        return (
            f"() => Array.from(document.querySelectorAll({sel}))."
            "map(el => ({tag: el.tagName, text: el.textContent}))"
        )
    raise AdapterStepFailed(f"helper {helper!r} not handled (registry whitelist drift)")
