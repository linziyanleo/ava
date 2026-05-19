"""Local site-adapter registry for the browser substrate (AVA-58).

* Storage: ``~/.ava/browser-sites/<adapter_id>/adapter.toml`` (configurable
  via :class:`BrowserSubstrateConfig.adapter_dir`).
* v1 only loads ``read_only=true`` adapters from inside the configured root.
* No network during load (Q5 / spec §1.4): adapters are read off disk; no
  git clone / HTTP fetch / dynamic import.
* Approved step kinds (plan §A5):
  ``browser_fetch``, ``browser_snapshot``, ``browser_evaluate_readonly``,
  ``set_var``, ``extract_jsonpath``. Unknown kinds reject the manifest.

The runner that *executes* the steps lives in :mod:`adapter_runner`; this
module only validates and indexes the manifest.
"""

from __future__ import annotations

import os
import tomllib
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

_APPROVED_STEP_KINDS: frozenset[str] = frozenset(
    {
        "browser_fetch",
        "browser_snapshot",
        "browser_evaluate_readonly",
        "set_var",
        "extract_jsonpath",
    }
)
_APPROVED_EVAL_HELPERS: frozenset[str] = frozenset(
    {"text_content", "inner_text", "attribute", "query_selector_all"}
)
_REQUIRED_TOP_FIELDS: tuple[str, ...] = (
    "id",
    "name",
    "domains",
    "description",
    "read_only",
    "args_schema",
    "steps",
)


class AdapterRejected(ValueError):
    """Raised when a manifest fails validation."""


@dataclass(frozen=True)
class SiteAdapterStep:
    kind: str
    params: dict[str, Any]


@dataclass(frozen=True)
class SiteAdapterManifest:
    id: str
    name: str
    domains: tuple[str, ...]
    description: str
    read_only: bool
    args_schema: dict[str, Any]
    steps: tuple[SiteAdapterStep, ...]
    output_schema: dict[str, Any] | None
    source_path: Path

    def to_summary(self) -> dict[str, Any]:
        return {
            "id": self.id,
            "name": self.name,
            "domains": list(self.domains),
            "description": self.description,
            "read_only": self.read_only,
        }

    def to_info(self) -> dict[str, Any]:
        return {
            **self.to_summary(),
            "args_schema": self.args_schema,
            "output_schema": self.output_schema,
            "steps": [{"kind": s.kind, **s.params} for s in self.steps],
        }


def _expand(path: str) -> Path:
    return Path(os.path.expanduser(str(path))).resolve()


def _validate_step(raw: Any, *, manifest_id: str, idx: int) -> SiteAdapterStep:
    if not isinstance(raw, dict):
        raise AdapterRejected(
            f"adapter {manifest_id!r} step #{idx} must be a TOML table, got {type(raw).__name__}"
        )
    kind = raw.get("kind")
    if not isinstance(kind, str) or kind not in _APPROVED_STEP_KINDS:
        raise AdapterRejected(
            f"adapter {manifest_id!r} step #{idx} kind {kind!r} is not in approved set "
            f"{sorted(_APPROVED_STEP_KINDS)}"
        )
    params = {k: v for k, v in raw.items() if k != "kind"}
    if kind == "browser_evaluate_readonly":
        helper = params.get("helper")
        if helper not in _APPROVED_EVAL_HELPERS:
            raise AdapterRejected(
                f"adapter {manifest_id!r} step #{idx}: browser_evaluate_readonly helper "
                f"{helper!r} is not in whitelist {sorted(_APPROVED_EVAL_HELPERS)}"
            )
    return SiteAdapterStep(kind=kind, params=params)


def _validate_manifest(raw: dict[str, Any], source_path: Path) -> SiteAdapterManifest:
    missing = [f for f in _REQUIRED_TOP_FIELDS if f not in raw]
    if missing:
        raise AdapterRejected(
            f"adapter at {source_path}: missing required field(s) {missing}"
        )

    adapter_id = raw["id"]
    if not isinstance(adapter_id, str) or not adapter_id.strip():
        raise AdapterRejected(f"adapter at {source_path}: `id` must be a non-empty string")

    if not isinstance(raw["read_only"], bool):
        raise AdapterRejected(f"adapter {adapter_id!r}: `read_only` must be a boolean")
    if raw["read_only"] is not True:
        raise AdapterRejected(
            f"adapter {adapter_id!r}: `read_only=false` is not supported in v1"
        )

    domains_raw = raw["domains"]
    if not isinstance(domains_raw, list) or not all(
        isinstance(d, str) and d for d in domains_raw
    ):
        raise AdapterRejected(
            f"adapter {adapter_id!r}: `domains` must be a list of non-empty strings"
        )

    args_schema = raw["args_schema"]
    if not isinstance(args_schema, dict):
        raise AdapterRejected(f"adapter {adapter_id!r}: `args_schema` must be a TOML table")

    output_schema = raw.get("output_schema")
    if output_schema is not None and not isinstance(output_schema, dict):
        raise AdapterRejected(
            f"adapter {adapter_id!r}: `output_schema` must be a TOML table when set"
        )

    steps_raw = raw["steps"]
    if not isinstance(steps_raw, list) or not steps_raw:
        raise AdapterRejected(
            f"adapter {adapter_id!r}: `steps` must be a non-empty list"
        )
    steps = tuple(
        _validate_step(s, manifest_id=adapter_id, idx=i)
        for i, s in enumerate(steps_raw)
    )

    return SiteAdapterManifest(
        id=adapter_id,
        name=str(raw["name"]),
        domains=tuple(domains_raw),
        description=str(raw["description"]),
        read_only=True,
        args_schema=args_schema,
        steps=steps,
        output_schema=output_schema,
        source_path=source_path,
    )


@dataclass
class SiteAdapterRegistry:
    """In-memory index over the local adapter directory."""

    adapter_dir: Path
    _manifests: dict[str, SiteAdapterManifest] = field(default_factory=dict)
    _errors: list[str] = field(default_factory=list)

    @classmethod
    def for_directory(cls, raw_dir: str | os.PathLike[str]) -> "SiteAdapterRegistry":
        return cls(adapter_dir=_expand(str(raw_dir)))

    # ----- loading ------------------------------------------------------

    def load(self) -> "SiteAdapterRegistry":
        """Walk ``adapter_dir`` and validate each ``adapter.toml``.

        No network calls happen here. Filesystem only.
        """
        self._manifests.clear()
        self._errors.clear()
        root = self.adapter_dir
        if not root.exists():
            return self
        if not root.is_dir():
            self._errors.append(f"adapter_dir {root} is not a directory")
            return self

        resolved_root = root.resolve()
        for entry in sorted(root.iterdir()):
            manifest_path = entry / "adapter.toml"
            if not manifest_path.is_file():
                continue
            try:
                resolved = manifest_path.resolve()
                # Reject symlinks/paths that escape adapter_dir.
                if resolved_root not in resolved.parents:
                    raise AdapterRejected(
                        f"manifest path {resolved} escapes adapter_dir {resolved_root}"
                    )
                with manifest_path.open("rb") as fh:
                    raw = tomllib.load(fh)
                if not isinstance(raw, dict):
                    raise AdapterRejected("manifest must be a TOML table at top level")
                manifest = _validate_manifest(raw, resolved)
                if manifest.id in self._manifests:
                    raise AdapterRejected(
                        f"duplicate adapter id {manifest.id!r} (also in "
                        f"{self._manifests[manifest.id].source_path})"
                    )
                self._manifests[manifest.id] = manifest
            except (AdapterRejected, tomllib.TOMLDecodeError, OSError) as exc:
                self._errors.append(f"{manifest_path}: {exc}")
        return self

    # ----- introspection ------------------------------------------------

    @property
    def errors(self) -> tuple[str, ...]:
        return tuple(self._errors)

    def list(self) -> list[SiteAdapterManifest]:
        return sorted(self._manifests.values(), key=lambda m: m.id)

    def get(self, adapter_id: str) -> SiteAdapterManifest | None:
        return self._manifests.get(adapter_id)

    def is_empty(self) -> bool:
        return not self._manifests

    def empty_hint(self) -> str:
        return (
            f"No site adapters found in {self.adapter_dir}. Drop a TOML manifest "
            f"at {self.adapter_dir}/<adapter_id>/adapter.toml with `read_only = true` "
            "and approved step kinds; v1 does not auto-fetch community adapters."
        )
