"""Helpers for Ava's overlay-style runtime config."""

from __future__ import annotations

import copy
import json
from pathlib import Path
from typing import Any

from ava.runtime import paths as runtime_paths

_NO_CHANGE = object()


def _resolve(path: Path) -> Path:
    return path.expanduser().resolve(strict=False)


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(data, indent=2, ensure_ascii=False) + "\n",
        encoding="utf-8",
    )


def uses_overlay_config(path: Path | None = None) -> bool:
    current = _resolve(path or runtime_paths.get_config_path())
    active = _resolve(runtime_paths.get_config_path())
    if current != active:
        return False
    return runtime_paths.resolve_ava_home() != runtime_paths.resolve_legacy_home()


def _deep_merge(base: Any, overlay: Any) -> Any:
    if not isinstance(base, dict) or not isinstance(overlay, dict):
        return copy.deepcopy(overlay)

    merged = copy.deepcopy(base)
    for key, value in overlay.items():
        if key in merged:
            merged[key] = _deep_merge(merged[key], value)
        else:
            merged[key] = copy.deepcopy(value)
    return merged


def _deep_diff(base: Any, target: Any) -> Any:
    if isinstance(base, dict) and isinstance(target, dict):
        diff: dict[str, Any] = {}
        for key, value in target.items():
            if key not in base:
                diff[key] = copy.deepcopy(value)
                continue

            nested = _deep_diff(base[key], value)
            if nested is not _NO_CHANGE:
                diff[key] = nested
        return diff or _NO_CHANGE

    if base == target:
        return _NO_CHANGE
    return copy.deepcopy(target)


def get_legacy_config_path() -> Path:
    return runtime_paths.resolve_legacy_home() / "config.json"


def get_extra_config_path() -> Path:
    return runtime_paths.get_extra_config_path()


def load_base_config_data() -> dict[str, Any]:
    legacy_path = get_legacy_config_path()
    if not legacy_path.exists():
        return {}
    return _read_json(legacy_path)


def load_effective_config_data(config_path: Path | None = None) -> dict[str, Any]:
    path = _resolve(config_path or runtime_paths.get_config_path())
    if not uses_overlay_config(path):
        if not path.exists():
            return {}
        return _read_json(path)

    merged: dict[str, Any] = load_base_config_data()
    if path.exists():
        merged = _deep_merge(merged, _read_json(path))

    extra_path = get_extra_config_path()
    if extra_path.exists():
        merged = _deep_merge(merged, _read_json(extra_path))
    return merged


def compute_overlay_data(
    effective_data: dict[str, Any],
    config_path: Path | None = None,
) -> dict[str, Any]:
    path = _resolve(config_path or runtime_paths.get_config_path())
    if not uses_overlay_config(path):
        return copy.deepcopy(effective_data)

    base = load_base_config_data()
    extra_path = get_extra_config_path()
    if extra_path.exists():
        base = _deep_merge(base, _read_json(extra_path))

    diff = _deep_diff(base, effective_data)
    if diff is _NO_CHANGE:
        return {}
    return diff


def normalize_config_overlay(config_path: Path | None = None) -> dict[str, Any]:
    path = _resolve(config_path or runtime_paths.get_config_path())
    overlay = compute_overlay_data(load_effective_config_data(path), path)
    write_json(path, overlay)
    return overlay
