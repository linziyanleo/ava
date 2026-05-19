"""DSL validator (AVA-47 P2a, AVA-25 P2b)."""
from __future__ import annotations

import pytest

from ava.console.services.workflow_definition_schema import (
    A2A_PREFIX,
    ACCEPTED_STEP_KINDS,
    JOIN_MERGE_STRATEGIES,
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


# ---------------------------------------------------------------------------
# AVA-25 P2b — parallel / join unlocks


def test_parallel_and_join_kinds_no_longer_reserved():
    assert "parallel" not in RESERVED_KIND_REJECT
    assert "join" not in RESERVED_KIND_REJECT
    assert "parallel" in ACCEPTED_STEP_KINDS
    assert "join" in ACCEPTED_STEP_KINDS
    assert "agent_task" in ACCEPTED_STEP_KINDS


def test_join_merge_closed_set():
    assert JOIN_MERGE_STRATEGIES == frozenset({"concat", "merge-objects", "last-success"})


def test_valid_fan_out_then_fan_in():
    payload = {
        "name": "fan",
        "steps": [
            _minimal_step(id="seed"),
            {"id": "fork", "kind": "parallel", "branches": ["b1", "b2"]},
            _minimal_step(id="b1", inputs={"v": "$.steps.seed.outputs.result"}),
            _minimal_step(id="b2", inputs={"v": "$.steps.seed.outputs.result"}),
            {"id": "merge", "kind": "join", "wait_for": ["b1", "b2"], "merge": "concat"},
            _minimal_step(id="tail", inputs={"v": "$.steps.merge.outputs.result"}),
        ],
    }
    wf = validate_definition(payload)
    assert {s.kind for s in wf.steps} == {"agent_task", "parallel", "join"}


def test_parallel_requires_branches():
    with pytest.raises(ValidationError, match="non-empty branches"):
        validate_definition({
            "name": "no-branches",
            "steps": [{"id": "fork", "kind": "parallel", "branches": []}],
        })


def test_parallel_unknown_branch_rejected():
    with pytest.raises(ValidationError, match="unknown step"):
        validate_definition({
            "name": "ghost-branch",
            "steps": [
                {"id": "fork", "kind": "parallel", "branches": ["nope"]},
            ],
        })


def test_parallel_branch_must_be_downstream():
    with pytest.raises(ValidationError, match="downstream"):
        validate_definition({
            "name": "back-branch",
            "steps": [
                _minimal_step(id="prior"),
                {"id": "fork", "kind": "parallel", "branches": ["prior"]},
            ],
        })


def test_parallel_self_branch_rejected():
    with pytest.raises(ValidationError):
        validate_definition({
            "name": "self-branch",
            "steps": [{"id": "fork", "kind": "parallel", "branches": ["fork"]}],
        })


def test_parallel_branches_must_be_unique():
    with pytest.raises(ValidationError, match="unique"):
        validate_definition({
            "name": "dup-branches",
            "steps": [
                {"id": "fork", "kind": "parallel", "branches": ["b", "b"]},
                _minimal_step(id="b"),
            ],
        })


def test_parallel_must_not_carry_agent_or_task():
    with pytest.raises(ValidationError, match="must not declare"):
        validate_definition({
            "name": "bad-parallel",
            "steps": [
                {
                    "id": "fork", "kind": "parallel", "branches": ["b"],
                    "agent": "codex",
                },
                _minimal_step(id="b"),
            ],
        })


def test_join_requires_wait_for_and_merge():
    with pytest.raises(ValidationError, match="non-empty wait_for"):
        validate_definition({
            "name": "no-wait",
            "steps": [
                _minimal_step(id="a"),
                {"id": "j", "kind": "join", "wait_for": [], "merge": "concat"},
            ],
        })
    with pytest.raises(ValidationError, match="merge"):
        validate_definition({
            "name": "no-merge",
            "steps": [
                _minimal_step(id="a"),
                {"id": "j", "kind": "join", "wait_for": ["a"]},
            ],
        })


def test_join_unknown_upstream_rejected():
    with pytest.raises(ValidationError, match="unknown step"):
        validate_definition({
            "name": "ghost-wait",
            "steps": [
                _minimal_step(id="a"),
                {"id": "j", "kind": "join", "wait_for": ["nope"], "merge": "concat"},
            ],
        })


def test_join_wait_for_must_be_upstream():
    with pytest.raises(ValidationError, match="upstream"):
        validate_definition({
            "name": "fwd-wait",
            "steps": [
                {"id": "j", "kind": "join", "wait_for": ["b"], "merge": "concat"},
                _minimal_step(id="b"),
            ],
        })


def test_join_merge_strategy_outside_closed_set_rejected():
    with pytest.raises(ValidationError, match="merge"):
        validate_definition({
            "name": "bad-merge",
            "steps": [
                _minimal_step(id="a"),
                {
                    "id": "j", "kind": "join",
                    "wait_for": ["a"], "merge": "first-success",
                },
            ],
        })


@pytest.mark.parametrize("merge", sorted(JOIN_MERGE_STRATEGIES))
def test_each_merge_strategy_accepted(merge: str):
    payload = {
        "name": f"merge-{merge}",
        "steps": [
            _minimal_step(id="a"),
            {"id": "j", "kind": "join", "wait_for": ["a"], "merge": merge},
        ],
    }
    wf = validate_definition(payload)
    assert wf.steps[1].merge == merge


def test_for_each_still_reserved_for_p2b_followups():
    """`for_each` is the P2b deferred sub-feature; rejected schema-side until
    a future ticket re-opens it."""
    assert RESERVED_KIND_REJECT["for_each"] == ("AVA-25", "P2b")
    with pytest.raises(ValidationError, match="for_each"):
        validate_definition({
            "name": "fe", "steps": [_minimal_step(kind="for_each")],
        })


def test_p3_kinds_still_rejected_with_ticket_message():
    """conditional / loop / approval / nested all map to AVA-31 / P3."""
    for kind, (ticket, phase) in RESERVED_KIND_REJECT.items():
        if ticket != "AVA-31":
            continue
        with pytest.raises(ValidationError) as exc_info:
            validate_definition({
                "name": "p3", "steps": [_minimal_step(kind=kind)],
            })
        assert ticket in str(exc_info.value)
        assert phase in str(exc_info.value)
