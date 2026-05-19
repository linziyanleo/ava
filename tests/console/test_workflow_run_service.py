"""Single-step linear-chain runner (AVA-47 P2a)."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ava.console.services.workflow_definition_schema import validate_definition
from ava.console.services.workflow_definition_store import WorkflowDefinitionStore
from ava.console.services.workflow_run_service import (
    AgentUnsupportedError,
    BackgroundTaskDispatcher,
    RunContext,
    StepDispatch,
    StepRuntimeError,
    WorkflowRunService,
    build_dispatch,
    render_prompt,
    resolve_jsonpath,
)
from ava.storage.database import Database


class _RecordingDispatcher:
    """Captures every dispatch for inspection."""

    def __init__(self) -> None:
        self.calls: list[StepDispatch] = []

    def dispatch(self, dispatch, *, run_id, step_run_id):
        self.calls.append(dispatch)
        return f"bg_{step_run_id[:6]}"


@pytest.fixture
def store(tmp_path: Path) -> WorkflowDefinitionStore:
    db = Database(tmp_path / "wf.db")
    return WorkflowDefinitionStore(db)


@pytest.fixture
def linear_definition_json() -> str:
    return json.dumps({
        "name": "review then apply",
        "inputs": [{"name": "repo_url"}],
        "outputs": [{"name": "applied_summary"}],
        "steps": [
            {
                "id": "s1", "kind": "agent_task", "agent": "codex",
                "task": {"prompt_template": "Review {{repo_url}}"},
                "inputs": {"repo_url": "$.inputs.repo_url"},
                "outputs": ["review_md"],
            },
            {
                "id": "s2", "kind": "agent_task", "agent": "nanobot",
                "task": {"prompt_template": "Apply {{review}}"},
                "inputs": {"review": "$.steps.s1.outputs.review_md"},
                "outputs": ["applied_summary"],
            },
        ],
    })


def test_six_migration_markers_stamped(tmp_path: Path):
    """All P2a tables must carry a versioned schema_migrations marker."""
    db = Database(tmp_path / "markers.db")
    rows = db.fetchall(
        "SELECT name FROM schema_migrations WHERE name LIKE '%_v1' ORDER BY name"
    )
    names = {row["name"] for row in rows}
    assert names == {
        "agent_workflows_v1", "workflow_versions_v1", "workflow_runs_v1",
        "workflow_steps_v1", "workflow_artifacts_v1", "workspace_leases_v1",
    }


def test_resolve_jsonpath_supports_inputs_workspace_steps():
    ctx = RunContext(
        inputs={"repo": "github.com/x/y"},
        workspace={"root": "/ws"},
        steps={"s1": {"outputs": {"review_md": "md"}}},
    )
    assert resolve_jsonpath("$.inputs.repo", ctx) == "github.com/x/y"
    assert resolve_jsonpath("$.workspace.root", ctx) == "/ws"
    assert resolve_jsonpath("$.steps.s1.outputs.review_md", ctx) == "md"


def test_resolve_jsonpath_missing_input_raises():
    ctx = RunContext(inputs={}, workspace={}, steps={})
    with pytest.raises(StepRuntimeError, match="missing"):
        resolve_jsonpath("$.inputs.nope", ctx)


def test_render_prompt_substitutes_resolved_inputs():
    ctx = RunContext(inputs={}, workspace={}, steps={})
    rendered = render_prompt(
        "Run {{repo}} via {{tool}}",
        ctx,
        {"repo": "github.com/x/y", "tool": "codex"},
    )
    assert rendered == "Run github.com/x/y via codex"


def test_a2a_agent_fail_fast_at_runner():
    wf = validate_definition({
        "name": "a2a",
        "steps": [
            {"id": "s1", "kind": "agent_task", "agent": "a2a://remote/codex",
             "task": {"prompt_template": "Hi"}},
        ],
    })
    ctx = RunContext(inputs={}, workspace={}, steps={})
    with pytest.raises(AgentUnsupportedError):
        build_dispatch(wf.steps[0], ctx)


@pytest.mark.parametrize("agent", ["codex", "claude_code", "image_gen", "nanobot"])
def test_runner_dispatches_each_local_agent(
    store: WorkflowDefinitionStore, agent: str
):
    definition = json.dumps({
        "name": f"single-{agent}",
        "steps": [
            {"id": "only", "kind": "agent_task", "agent": agent,
             "task": {"prompt_template": "hello"}, "outputs": ["result"]},
        ],
    })
    wf, _ = store.create_workflow(name=f"single-{agent}", definition_json=definition)
    dispatcher = _RecordingDispatcher()
    service = WorkflowRunService(store=store, dispatcher=dispatcher)
    run = service.start_run(workflow_id=wf.workflow_id, version=1)
    assert run.status == "succeeded"
    assert len(dispatcher.calls) == 1
    assert dispatcher.calls[0].task_type == agent


def test_linear_chain_passes_outputs_downstream(
    store: WorkflowDefinitionStore, linear_definition_json: str
):
    wf, _ = store.create_workflow(name="demo", definition_json=linear_definition_json)
    dispatcher = _RecordingDispatcher()
    service = WorkflowRunService(store=store, dispatcher=dispatcher)
    run = service.start_run(
        workflow_id=wf.workflow_id, version=1, inputs={"repo_url": "github.com/x/y"},
    )
    assert run.status == "succeeded"
    assert len(dispatcher.calls) == 2
    assert dispatcher.calls[0].task_type == "codex"
    assert "github.com/x/y" in dispatcher.calls[0].prompt
    # Step 2 prompt must include the synthesised step 1 output reference.
    assert dispatcher.calls[1].task_type == "nanobot"
    assert "<bg_" in dispatcher.calls[1].prompt


def test_lease_released_after_step(
    store: WorkflowDefinitionStore, linear_definition_json: str
):
    wf, _ = store.create_workflow(name="demo", definition_json=linear_definition_json)
    service = WorkflowRunService(store=store, dispatcher=_RecordingDispatcher())
    service.start_run(workflow_id=wf.workflow_id, version=1, inputs={"repo_url": "x"})
    assert store.list_active_leases() == []


def test_a2a_failure_marks_run_failed_and_persists_error(
    store: WorkflowDefinitionStore,
):
    definition = json.dumps({
        "name": "a2a only",
        "steps": [
            {"id": "s1", "kind": "agent_task", "agent": "a2a://remote/x",
             "task": {"prompt_template": "Hi"}},
        ],
    })
    wf, _ = store.create_workflow(name="a2a", definition_json=definition)
    service = WorkflowRunService(store=store, dispatcher=_RecordingDispatcher())
    with pytest.raises(StepRuntimeError) as exc_info:
        service.start_run(workflow_id=wf.workflow_id, version=1)
    assert exc_info.value.code == "agent_unsupported"
    runs = store.list_runs_for_workflow(wf.workflow_id)
    assert len(runs) == 1
    assert runs[0].status == "failed"


def test_unresolvable_input_marks_step_failed(store: WorkflowDefinitionStore):
    definition = json.dumps({
        "name": "missing-input",
        "steps": [
            {"id": "s1", "kind": "agent_task", "agent": "codex",
             "task": {"prompt_template": "X {{missing}}"},
             "inputs": {"missing": "$.inputs.never_provided"}},
        ],
    })
    wf, _ = store.create_workflow(name="bad", definition_json=definition)
    service = WorkflowRunService(store=store, dispatcher=_RecordingDispatcher())
    with pytest.raises(StepRuntimeError):
        service.start_run(workflow_id=wf.workflow_id, version=1)
    steps = store.list_steps_for_run(
        store.list_runs_for_workflow(wf.workflow_id)[0].run_id
    )
    assert steps[0].status == "failed"


def test_base_version_optimistic_concurrency(
    store: WorkflowDefinitionStore, linear_definition_json: str
):
    wf, _ = store.create_workflow(name="cc", definition_json=linear_definition_json)
    v2 = store.update_workflow(
        workflow_id=wf.workflow_id, base_version=1,
        definition_json=linear_definition_json, change_summary="bump",
    )
    assert v2.version == 2
    # Stale base_version should be refused.
    with pytest.raises(ValueError, match="base_version"):
        store.update_workflow(
            workflow_id=wf.workflow_id, base_version=1,
            definition_json=linear_definition_json, change_summary="stale",
        )
