"""Tests for built-in workflow templates loader (AVA-48 plan-step-7)."""

from __future__ import annotations

from ava.console.services.workflow_templates_loader import (
    get_template,
    list_templates,
)


def test_lists_two_built_in_templates() -> None:
    out = list_templates()
    ids = {t["id"] for t in out}
    assert {"codex_review_then_apply", "image_gen_then_caption"} <= ids


def test_each_template_passes_v1_validator() -> None:
    # `_read_template` already calls `validate_definition`; if any template
    # was structurally invalid it would have been silently dropped. Assert
    # that nothing was dropped by counting against the file system glob.
    from pathlib import Path

    templates_dir = Path(__file__).resolve().parents[2] / "ava" / "console" / "services" / "workflow_templates"
    json_files = sorted(templates_dir.glob("*.json"))
    assert len(json_files) >= 2
    out = list_templates()
    assert len(out) == len(json_files), (
        f"expected all {len(json_files)} built-in templates to validate, got {len(out)}"
    )


def test_template_definition_steps_are_linear_v1_compatible() -> None:
    for tpl in list_templates():
        steps = tpl["definition"]["steps"]
        assert len(steps) >= 1
        assert all(s["kind"] == "agent_task" for s in steps), (
            f"template {tpl['id']} has non-agent_task step (v1 closed set violation)"
        )


def test_get_template_by_id() -> None:
    assert get_template("codex_review_then_apply") is not None
    assert get_template("ghost") is None
