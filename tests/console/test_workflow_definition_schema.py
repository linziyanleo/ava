"""DSL v1 validator (AVA-47 P2a)."""
from __future__ import annotations

import pytest

from ava.console.services.workflow_definition_schema import (
    A2A_PREFIX,
    LOCAL_AGENTS,
    RESERVED_KIND_REJECT,
    ValidationError,
    is_a2a_agent,
    validate_definition,
)


def _minimal_step(**overrides):
    base = {
        "id": "step_1",
        "kind": "agent_task",
        "agent": "codex",
        "task": {"prompt_template": "do {{thing}}"},
        "outputs": ["result"],
    }
    base.update(overrides)
    return base


def test_valid_two_step_chain():
    payload = {
        "name": "demo",
        "inputs": [{"name": "repo_url"}],
        "outputs": [{"name": "applied"}],
        "steps": [
            _minimal_step(id="s1", outputs=["review_md"]),
            _minimal_step(
                id="s2", agent="nanobot",
                task={"prompt_template": "Apply {{review}}"},
                inputs={"review": "$.steps.s1.outputs.review_md"},
                outputs=["applied"],
            ),
        ],
    }
    wf = validate_definition(payload)
    assert wf.name == "demo"
    assert len(wf.steps) == 2


@pytest.mark.parametrize("forbidden_kind", sorted(RESERVED_KIND_REJECT))
def test_reserved_kinds_rejected_with_ticket_reference(forbidden_kind):
    ticket, phase = RESERVED_KIND_REJECT[forbidden_kind]
    payload = {
        "name": "bad",
        "steps": [_minimal_step(kind=forbidden_kind)],
    }
    with pytest.raises(ValidationError) as exc_info:
        validate_definition(payload)
    message = str(exc_info.value)
    assert ticket in message, f"error must name {ticket}: {message}"
    assert phase in message, f"error must name {phase}: {message}"


def test_unknown_kind_rejected():
    with pytest.raises(ValidationError):
        validate_definition({
            "name": "bad", "steps": [_minimal_step(kind="something_random")]
        })


def test_a2a_agent_accepted_at_schema_layer():
    payload = {
        "name": "a2a",
        "steps": [_minimal_step(agent="a2a://remote-host/some-agent")],
    }
    wf = validate_definition(payload)
    assert wf.steps[0].agent.startswith(A2A_PREFIX)
    assert is_a2a_agent(wf.steps[0].agent)


def test_a2a_agent_without_path_rejected():
    with pytest.raises(ValidationError):
        validate_definition({
            "name": "bad", "steps": [_minimal_step(agent="a2a://hostonly")],
        })


def test_local_agents_accepted():
    for agent in sorted(LOCAL_AGENTS):
        wf = validate_definition({
            "name": f"single-{agent}",
            "steps": [_minimal_step(agent=agent)],
        })
        assert wf.steps[0].agent == agent


def test_duplicate_step_id_rejected():
    with pytest.raises(ValidationError, match="duplicate step.id"):
        validate_definition({
            "name": "dup",
            "steps": [_minimal_step(id="s1"), _minimal_step(id="s1")],
        })


def test_next_must_reference_known_step():
    with pytest.raises(ValidationError, match="next='nope'"):
        validate_definition({
            "name": "bad-next",
            "steps": [_minimal_step(id="s1", next="nope")],
        })


def test_forward_reference_rejected():
    with pytest.raises(ValidationError, match="downstream/unknown"):
        validate_definition({
            "name": "fwd",
            "steps": [
                _minimal_step(id="s1", inputs={"x": "$.steps.s2.outputs.y"}),
                _minimal_step(id="s2"),
            ],
        })


def test_self_reference_rejected():
    with pytest.raises(ValidationError, match="cannot reference its own"):
        validate_definition({
            "name": "self",
            "steps": [_minimal_step(id="s1", inputs={"x": "$.steps.s1.outputs.y"})],
        })


def test_inputs_jsonpath_shape_enforced():
    with pytest.raises(ValidationError, match="JSONPath"):
        validate_definition({
            "name": "bad-input",
            "steps": [_minimal_step(inputs={"x": "not_a_path"})],
        })


def test_extra_fields_rejected():
    """Strict schema — typos must surface, not silently drop."""
    with pytest.raises(ValidationError):
        validate_definition({
            "name": "extra",
            "steps": [
                {**_minimal_step(), "unknown_field": "leak"},
            ],
        })


def test_step_id_must_be_identifier():
    with pytest.raises(ValidationError):
        validate_definition({
            "name": "id",
            "steps": [_minimal_step(id="not-an-identifier")],
        })


def test_workflow_must_have_at_least_one_step():
    with pytest.raises(ValidationError):
        validate_definition({"name": "empty", "steps": []})
