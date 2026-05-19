"""Tests for SiteAdapterRegistry (AVA-58, plan §F step 6)."""

from __future__ import annotations

from pathlib import Path
from unittest import mock

import pytest

from ava.tools.browser_substrate.adapter_registry import (
    AdapterRejected,
    SiteAdapterRegistry,
    _validate_manifest,
)


_VALID_TOML = """\
id = "demo"
name = "Demo Adapter"
domains = ["example.test"]
description = "A demo adapter for tests."
read_only = true

[args_schema]
type = "object"

[args_schema.properties.q]
type = "string"

[[steps]]
kind = "browser_fetch"
url = "/api/items"
method = "GET"

[[steps]]
kind = "extract_jsonpath"
path = "$.items[*]"
output_var = "items"
"""


def _write_adapter(tmp_path: Path, adapter_id: str, body: str) -> Path:
    sub = tmp_path / adapter_id
    sub.mkdir()
    p = sub / "adapter.toml"
    p.write_text(body)
    return p


# ----- happy path ------------------------------------------------------


def test_loads_valid_adapter(tmp_path: Path) -> None:
    _write_adapter(tmp_path, "demo", _VALID_TOML)
    reg = SiteAdapterRegistry.for_directory(tmp_path).load()
    assert reg.errors == ()
    listed = reg.list()
    assert len(listed) == 1
    assert listed[0].id == "demo"
    assert listed[0].read_only is True
    assert [s.kind for s in listed[0].steps] == ["browser_fetch", "extract_jsonpath"]


def test_to_summary_and_to_info_shape(tmp_path: Path) -> None:
    _write_adapter(tmp_path, "demo", _VALID_TOML)
    reg = SiteAdapterRegistry.for_directory(tmp_path).load()
    m = reg.get("demo")
    assert m is not None
    summary = m.to_summary()
    assert summary["id"] == "demo"
    info = m.to_info()
    assert info["args_schema"]["type"] == "object"
    assert info["steps"][0]["kind"] == "browser_fetch"
    assert info["steps"][0]["url"] == "/api/items"


# ----- safety boundary -------------------------------------------------


def test_read_only_false_rejected(tmp_path: Path) -> None:
    body = _VALID_TOML.replace("read_only = true", "read_only = false")
    _write_adapter(tmp_path, "bad", body)
    reg = SiteAdapterRegistry.for_directory(tmp_path).load()
    assert reg.list() == []
    assert any("read_only=false" in e for e in reg.errors)


def test_missing_required_field_rejected(tmp_path: Path) -> None:
    body = _VALID_TOML.replace('id = "demo"\n', "")
    _write_adapter(tmp_path, "demo", body)
    reg = SiteAdapterRegistry.for_directory(tmp_path).load()
    assert reg.list() == []
    assert any("missing required field" in e for e in reg.errors)


def test_unknown_step_kind_rejected(tmp_path: Path) -> None:
    body = _VALID_TOML.replace('kind = "browser_fetch"', 'kind = "execute_script"')
    _write_adapter(tmp_path, "demo", body)
    reg = SiteAdapterRegistry.for_directory(tmp_path).load()
    assert reg.list() == []
    assert any("not in approved set" in e for e in reg.errors)


def test_browser_evaluate_readonly_helper_whitelist(tmp_path: Path) -> None:
    body = """\
id = "ev"
name = "Eval"
domains = ["example.test"]
description = "uses readonly eval"
read_only = true
[args_schema]
type = "object"
[[steps]]
kind = "browser_evaluate_readonly"
helper = "fetch"
"""
    _write_adapter(tmp_path, "ev", body)
    reg = SiteAdapterRegistry.for_directory(tmp_path).load()
    assert reg.list() == []
    assert any("helper" in e and "whitelist" in e for e in reg.errors)


def test_duplicate_id_rejected(tmp_path: Path) -> None:
    _write_adapter(tmp_path, "first", _VALID_TOML)
    _write_adapter(tmp_path, "second", _VALID_TOML)  # same id="demo" inside
    reg = SiteAdapterRegistry.for_directory(tmp_path).load()
    assert len(reg.list()) == 1
    assert any("duplicate" in e for e in reg.errors)


def test_invalid_toml_rejected(tmp_path: Path) -> None:
    _write_adapter(tmp_path, "broken", "not = valid = toml")
    reg = SiteAdapterRegistry.for_directory(tmp_path).load()
    assert reg.list() == []
    assert reg.errors


def test_steps_list_required_non_empty(tmp_path: Path) -> None:
    body = """\
id = "x"
name = "X"
domains = ["a.test"]
description = ""
read_only = true
args_schema = {}
steps = []
"""
    _write_adapter(tmp_path, "x", body)
    reg = SiteAdapterRegistry.for_directory(tmp_path).load()
    assert reg.list() == []
    assert any("non-empty list" in e for e in reg.errors)


# ----- bootstrap behavior (Q5) -----------------------------------------


def test_empty_dir_returns_empty_with_hint(tmp_path: Path) -> None:
    reg = SiteAdapterRegistry.for_directory(tmp_path).load()
    assert reg.list() == []
    assert reg.is_empty()
    assert "No site adapters found" in reg.empty_hint()


def test_missing_dir_returns_empty(tmp_path: Path) -> None:
    reg = SiteAdapterRegistry.for_directory(tmp_path / "absent").load()
    assert reg.list() == []
    assert reg.is_empty()
    # missing dir is OK — hint still useful for bootstrap
    assert "No site adapters" in reg.empty_hint()


# ----- no-network invariant (Q5 / spec §1.4) ---------------------------


def test_no_network_during_load(tmp_path: Path) -> None:
    _write_adapter(tmp_path, "demo", _VALID_TOML)
    with (
        mock.patch("urllib.request.urlopen", side_effect=AssertionError("urllib used")),
        mock.patch("socket.socket.connect", side_effect=AssertionError("socket connect")),
    ):
        try:
            import httpx  # noqa: F401

            with mock.patch("httpx.get", side_effect=AssertionError("httpx used")):
                reg = SiteAdapterRegistry.for_directory(tmp_path).load()
        except ImportError:
            reg = SiteAdapterRegistry.for_directory(tmp_path).load()
    assert reg.list() and reg.list()[0].id == "demo"


# ----- isolation: validate_manifest unit-test --------------------------


def test_validate_manifest_unit() -> None:
    raw = {
        "id": "u",
        "name": "U",
        "domains": ["x.test"],
        "description": "",
        "read_only": True,
        "args_schema": {},
        "steps": [{"kind": "set_var", "name": "k", "value": "v"}],
    }
    m = _validate_manifest(raw, Path("/tmp/u/adapter.toml"))
    assert m.id == "u"
    assert m.steps[0].kind == "set_var"
    assert m.steps[0].params == {"name": "k", "value": "v"}


def test_validate_manifest_rejects_non_string_domains() -> None:
    raw = {
        "id": "u",
        "name": "U",
        "domains": [1, 2],
        "description": "",
        "read_only": True,
        "args_schema": {},
        "steps": [{"kind": "set_var"}],
    }
    with pytest.raises(AdapterRejected, match="domains"):
        _validate_manifest(raw, Path("/tmp/u/adapter.toml"))
