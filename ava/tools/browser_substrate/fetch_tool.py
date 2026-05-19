"""``browser_fetch`` — read-only HTTP from the live browser context (AVA-58).

Safety boundary (task spec §0 Q3 + §1.4):

* Method allowlist: ``{GET, HEAD}``. Anything else is rejected before any MCP
  contact.
* Caller-supplied ``Cookie`` / ``Authorization`` / ``Origin`` headers are
  stripped (those come from the browser context, not the agent).
* Relative URLs are passed through to the browser, which resolves them against
  the active document. Absolute URLs require an explicit ``allowed_origins``
  list (v1: no auto-discovery of open tabs).
* The JS that performs the fetch is :data:`_FETCH_TEMPLATE`, a module-private
  constant. The tool only fills three JSON-encoded slots (URL / method /
  headers / with_body / body_max_bytes); no caller string is interpolated raw.
* Body capture is opt-in (``with_body=True``) and bounded by ``body_max_bytes``.
"""

from __future__ import annotations

import json
import re
from typing import Any
from urllib.parse import urlparse

from nanobot.agent.tools.base import Tool

from ava.tools.browser_substrate.client import BrowserSubstrateClient

_ALLOWED_METHODS: frozenset[str] = frozenset({"GET", "HEAD"})
_DENY_HEADERS: frozenset[str] = frozenset({"cookie", "authorization", "origin"})
_DEFAULT_BODY_MAX_BYTES = 65536

_FETCH_TEMPLATE: str = """\
async () => {
  const __URL__ = %(url)s;
  const __METHOD__ = %(method)s;
  const __HEADERS__ = %(headers)s;
  const __WITH_BODY__ = %(with_body)s;
  const __BODY_MAX__ = %(body_max)s;
  try {
    const resp = await fetch(__URL__, {
      method: __METHOD__,
      headers: __HEADERS__,
      credentials: 'include',
      redirect: 'follow',
    });
    const ct = resp.headers.get('content-type') || '';
    const out = {
      ok: true,
      url: resp.url,
      status: resp.status,
      headers: Object.fromEntries(resp.headers.entries()),
      content_type: ct,
      truncated: false,
      body: null,
      json: null,
    };
    if (__WITH_BODY__ && __METHOD__ !== 'HEAD') {
      let text = await resp.text();
      if (text.length > __BODY_MAX__) {
        text = text.slice(0, __BODY_MAX__);
        out.truncated = true;
      }
      out.body = text;
      if (ct.indexOf('application/json') !== -1) {
        try { out.json = JSON.parse(text); } catch (e) { /* non-JSON */ }
      }
    }
    return JSON.stringify(out);
  } catch (e) {
    return JSON.stringify({ ok: false, error: String(e && e.message || e) });
  }
}
"""


def _is_absolute(url: str) -> bool:
    parsed = urlparse(url)
    return bool(parsed.scheme and parsed.netloc)


def _origin_of(url: str) -> str:
    p = urlparse(url)
    if not p.scheme or not p.netloc:
        raise ValueError(f"cannot derive origin from {url!r}")
    return f"{p.scheme}://{p.netloc}"


def _strip_denylisted_headers(headers: dict[str, str]) -> tuple[dict[str, str], list[str]]:
    kept: dict[str, str] = {}
    stripped: list[str] = []
    for k, v in (headers or {}).items():
        if k.lower() in _DENY_HEADERS:
            stripped.append(k)
            continue
        kept[k] = v
    return kept, stripped


_RUNNER_ERROR_RE = re.compile(r"^\s*###?\s*Error|^\s*Error\b", re.IGNORECASE)


def _looks_like_runner_error(text: str) -> bool:
    return bool(_RUNNER_ERROR_RE.match(text or ""))


class BrowserFetchTool(Tool):
    """Read-only HTTP fetch from the active browser context."""

    def __init__(
        self,
        *,
        client: BrowserSubstrateClient,
        body_max_bytes: int = _DEFAULT_BODY_MAX_BYTES,
    ) -> None:
        if body_max_bytes <= 0:
            raise ValueError("body_max_bytes must be positive")
        self._client = client
        self._body_max_bytes = body_max_bytes

    # ----- Tool protocol ------------------------------------------------

    @property
    def name(self) -> str:
        return "browser_fetch"

    @property
    def description(self) -> str:
        return (
            "Read-only HTTP fetch (GET/HEAD) from the live browser context. "
            "Use for logged-in JSON/HTML APIs on the current page. Relative "
            "URLs resolve against the active document; absolute URLs require "
            "an explicit `allowed_origins` list. Body capture is opt-in and "
            "bounded — body may contain auth tokens, do not echo to untrusted "
            "destinations."
        )

    @property
    def parameters(self) -> dict[str, Any]:
        return {
            "type": "object",
            "properties": {
                "url": {
                    "type": "string",
                    "description": "Relative path resolved against the active "
                    "tab, or an absolute URL (must match `allowed_origins`).",
                },
                "method": {
                    "type": "string",
                    "enum": ["GET", "HEAD"],
                    "description": "HTTP method. v1 only allows GET/HEAD.",
                },
                "headers": {
                    "type": "object",
                    "description": "Caller-supplied request headers. "
                    "`Cookie`/`Authorization`/`Origin` are stripped — those "
                    "come from the browser context.",
                },
                "with_body": {
                    "type": "boolean",
                    "description": "Whether to return the response body. "
                    "Default false. Body is bounded by body_max_bytes.",
                },
                "allowed_origins": {
                    "type": "array",
                    "items": {"type": "string"},
                    "description": "Required for absolute URLs. Each entry is "
                    "an origin like 'https://example.com'.",
                },
            },
            "required": ["url"],
        }

    @property
    def read_only(self) -> bool:
        return True

    # ----- request validation ------------------------------------------

    def _validate_request(
        self,
        *,
        url: str,
        method: str,
        headers: dict[str, str] | None,
        allowed_origins: list[str] | None,
    ) -> tuple[str, dict[str, str], list[str]]:
        method_norm = (method or "GET").upper()
        if method_norm not in _ALLOWED_METHODS:
            raise ValueError(
                f"browser_fetch v1 only allows GET/HEAD; refusing {method_norm!r}"
            )

        if not isinstance(url, str) or not url.strip():
            raise ValueError("url is required")

        if _is_absolute(url):
            origin = _origin_of(url)
            if not allowed_origins:
                raise ValueError(
                    f"absolute URL {url!r} requires `allowed_origins`; "
                    "for same-origin requests pass a relative path instead."
                )
            if origin not in allowed_origins:
                raise ValueError(
                    f"absolute URL origin {origin!r} not in allowed_origins {list(allowed_origins)!r}"
                )

        kept, stripped = _strip_denylisted_headers(headers or {})
        return method_norm, kept, stripped

    # ----- execution ----------------------------------------------------

    def _build_eval_function(
        self,
        *,
        url: str,
        method: str,
        headers: dict[str, str],
        with_body: bool,
        body_max: int,
    ) -> str:
        return _FETCH_TEMPLATE % {
            "url": json.dumps(url),
            "method": json.dumps(method),
            "headers": json.dumps(headers),
            "with_body": "true" if with_body else "false",
            "body_max": json.dumps(body_max),
        }

    async def execute(self, **kwargs: Any) -> str:  # type: ignore[override]
        url = kwargs.get("url", "")
        method = kwargs.get("method", "GET")
        headers = kwargs.get("headers") or {}
        with_body = bool(kwargs.get("with_body", False))
        allowed_origins = kwargs.get("allowed_origins")

        try:
            method_norm, safe_headers, stripped = self._validate_request(
                url=url,
                method=method,
                headers=headers,
                allowed_origins=allowed_origins,
            )
        except ValueError as exc:
            return json.dumps({"ok": False, "error": str(exc)})

        body_max = self._body_max_bytes
        eval_fn = self._build_eval_function(
            url=url,
            method=method_norm,
            headers=safe_headers,
            with_body=with_body,
            body_max=body_max,
        )

        raw = await self._client.call_mcp("browser_evaluate", {"function": eval_fn})
        if _looks_like_runner_error(raw):
            return json.dumps({"ok": False, "error": raw.strip()})

        parsed: dict[str, Any]
        try:
            parsed = json.loads(raw)
            if not isinstance(parsed, dict):
                raise ValueError("expected object from browser_evaluate")
        except (ValueError, json.JSONDecodeError):
            # browser_evaluate sometimes wraps text — try to extract last JSON line
            for line in reversed(raw.splitlines()):
                line = line.strip()
                if line.startswith("{") and line.endswith("}"):
                    try:
                        parsed = json.loads(line)
                        if isinstance(parsed, dict):
                            break
                    except json.JSONDecodeError:
                        continue
            else:
                return json.dumps({
                    "ok": False,
                    "error": "browser_evaluate returned non-JSON",
                    "raw": raw[:512],
                })

        if not parsed.get("ok"):
            return json.dumps({"ok": False, "error": parsed.get("error", "fetch failed")})

        tab_key = f"{self._client.mcp_server_name}:active"
        seq = self._client.append_event(
            tab_key,
            "network",
            {
                "url": parsed.get("url", url),
                "method": method_norm,
                "status": parsed.get("status"),
                "content_type": parsed.get("content_type"),
                "truncated": parsed.get("truncated", False),
            },
        )
        self._client.mark_action_boundary(tab_key)

        out: dict[str, Any] = {
            "ok": True,
            "url": parsed.get("url", url),
            "status": parsed.get("status"),
            "headers": parsed.get("headers", {}),
            "content_type": parsed.get("content_type"),
            "truncated": parsed.get("truncated", False),
            "seq": seq,
            "cursor": str(seq + 1),
        }
        if with_body:
            out["body"] = parsed.get("body")
            if parsed.get("json") is not None:
                out["json"] = parsed.get("json")
        if stripped:
            out["stripped_headers"] = stripped
        return json.dumps(out)
