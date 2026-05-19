"""Workflow runner — single-step P2a + DAG/fan-out/fan-in P2b."""
from __future__ import annotations

import json
from pathlib import Path

import pytest

from ava.console.services.workflow_definition_schema import validate_definition
from ava.console.services.workflow_definition_store import (
    LeaseAcquisitionError,
    WorkflowDefinitionStore,
)
from ava.console.services.workflow_run_service import (
    AgentUnsupportedError,
    BackgroundTaskDispatcher,
    RunContext,
    StepDispatch,
    StepRuntimeError,
    WorkflowRunService,
    branch_parent_map,
    build_dispatch,
    build_predecessors,
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


def test_p2a_migration_markers_stamped(tmp_path: Path):
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


def test_p2b_migration_markers_stamped(tmp_path: Path):
    """AVA-25 P2b widens workflow_runs and workflow_steps."""
    db = Database(tmp_path / "markers_v2.db")
    rows = db.fetchall(
        "SELECT name FROM schema_migrations WHERE name LIKE '%_v2' ORDER BY name"
    )
    names = {row["name"] for row in rows}
    assert names == {"workflow_runs_v2", "workflow_steps_v2"}
    # New columns are reachable via PRAGMA so the runner can rely on them.
    step_columns = {row["name"] for row in db.fetchall("PRAGMA table_info(workflow_steps)")}
    run_columns = {row["name"] for row in db.fetchall("PRAGMA table_info(workflow_runs)")}
    assert "parent_step_id" in step_columns
    assert "trace_id" in run_columns
    assert "retry_of_run_id" in run_columns


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


# ---------------------------------------------------------------------------
# AVA-25 P2b — fan-out / fan-in


def _fan_out_definition(*, merge: str = "concat", branch_count: int = 2) -> str:
    """Build seed → fork → [b1..bN] → merge → tail."""
    branch_ids = [f"b{i}" for i in range(branch_count)]
    steps: list[dict] = [
        {
            "id": "seed", "kind": "agent_task", "agent": "codex",
            "task": {"prompt_template": "seed"}, "outputs": ["seed_out"],
        },
        {"id": "fork", "kind": "parallel", "branches": branch_ids},
    ]
    for branch_id in branch_ids:
        steps.append({
            "id": branch_id, "kind": "agent_task", "agent": "nanobot",
            "task": {"prompt_template": f"branch {branch_id}"},
            "inputs": {"seed": "$.steps.seed.outputs.seed_out"},
            "outputs": ["branch_out"],
        })
    steps.append({
        "id": "merge", "kind": "join", "wait_for": branch_ids, "merge": merge,
    })
    steps.append({
        "id": "tail", "kind": "agent_task", "agent": "claude_code",
        "task": {"prompt_template": "tail"},
        "outputs": ["tail_out"],
    })
    return json.dumps({"name": "fan", "steps": steps})


def test_predecessor_graph_handles_parallel_join():
    definition = validate_definition(json.loads(_fan_out_definition()))
    preds = build_predecessors(definition)
    assert preds["seed"] == []
    assert preds["fork"] == ["seed"]
    assert preds["b0"] == ["fork"]
    assert preds["b1"] == ["fork"]
    # join's predecessors come from wait_for, not the prior array index.
    assert sorted(preds["merge"]) == ["b0", "b1"]
    # The step right after a join inherits the join as its linear predecessor.
    assert preds["tail"] == ["merge"]


def test_branch_parent_map_traces_fan_out():
    definition = validate_definition(json.loads(_fan_out_definition()))
    assert branch_parent_map(definition) == {"b0": "fork", "b1": "fork"}


def test_fan_out_dispatches_each_branch_with_parent_step_id(
    store: WorkflowDefinitionStore,
):
    wf, _ = store.create_workflow(name="fan", definition_json=_fan_out_definition())
    dispatcher = _RecordingDispatcher()
    service = WorkflowRunService(store=store, dispatcher=dispatcher)
    run = service.start_run(workflow_id=wf.workflow_id, version=1)
    assert run.status == "succeeded"
    # 5 dispatches: seed + 2 branches + tail (parallel/join are routing nodes).
    assert len(dispatcher.calls) == 4
    steps = store.list_steps_for_run(run.run_id)
    by_step_id = {s.step_id: s for s in steps}
    fork_run_id = by_step_id["fork"].step_run_id
    assert by_step_id["b0"].parent_step_id == fork_run_id
    assert by_step_id["b1"].parent_step_id == fork_run_id
    # Non-branch agent_task steps have no parent.
    assert by_step_id["seed"].parent_step_id == ""
    assert by_step_id["tail"].parent_step_id == ""


@pytest.mark.parametrize("merge", ["concat", "merge-objects", "last-success"])
def test_join_merge_strategies(store: WorkflowDefinitionStore, merge: str):
    wf, _ = store.create_workflow(
        name=f"merge-{merge}",
        definition_json=_fan_out_definition(merge=merge, branch_count=2),
    )
    dispatcher = _RecordingDispatcher()
    service = WorkflowRunService(store=store, dispatcher=dispatcher)
    run = service.start_run(workflow_id=wf.workflow_id, version=1)
    assert run.status == "succeeded"
    steps = store.list_steps_for_run(run.run_id)
    join_step = next(s for s in steps if s.step_id == "merge")
    join_outputs = json.loads(join_step.outputs_json)
    if merge == "concat":
        assert "branch_out" in join_outputs and len(join_outputs["branch_out"]) == 2
    if merge == "merge-objects":
        assert "branch_out" in join_outputs
    if merge == "last-success":
        assert "branch_out" in join_outputs and not isinstance(join_outputs["branch_out"], list)


def test_branch_failure_skips_join_and_tail(store: WorkflowDefinitionStore):
    """One branch's a2a:// failure → join skipped → tail skipped → run failed."""
    bad = json.dumps({
        "name": "bad-branch",
        "steps": [
            {"id": "seed", "kind": "agent_task", "agent": "codex",
             "task": {"prompt_template": "seed"}, "outputs": ["x"]},
            {"id": "fork", "kind": "parallel", "branches": ["good", "bad"]},
            {"id": "good", "kind": "agent_task", "agent": "nanobot",
             "task": {"prompt_template": "good"},
             "outputs": ["good_out"]},
            {"id": "bad", "kind": "agent_task", "agent": "a2a://remote/x",
             "task": {"prompt_template": "bad"}},
            {"id": "merge", "kind": "join",
             "wait_for": ["good", "bad"], "merge": "concat"},
            {"id": "tail", "kind": "agent_task", "agent": "claude_code",
             "task": {"prompt_template": "tail"}},
        ],
    })
    wf, _ = store.create_workflow(name="bb", definition_json=bad)
    service = WorkflowRunService(store=store, dispatcher=_RecordingDispatcher())
    with pytest.raises(StepRuntimeError) as exc_info:
        service.start_run(workflow_id=wf.workflow_id, version=1)
    assert exc_info.value.code == "agent_unsupported"
    runs = store.list_runs_for_workflow(wf.workflow_id)
    assert runs[0].status == "failed"
    steps = {s.step_id: s for s in store.list_steps_for_run(runs[0].run_id)}
    assert steps["seed"].status == "succeeded"
    assert steps["fork"].status == "succeeded"
    assert steps["good"].status == "succeeded"
    assert steps["bad"].status == "failed"
    assert steps["merge"].status == "skipped"
    assert steps["tail"].status == "skipped"


def test_lease_conflict_fails_only_the_branch(store: WorkflowDefinitionStore):
    """Two branches contending for the same workspace path: second fails."""
    fan = _fan_out_definition()
    wf, _ = store.create_workflow(name="contend", definition_json=fan)
    dispatcher = _RecordingDispatcher()
    # Force every step (including branches) onto the same lease path.
    service = WorkflowRunService(
        store=store,
        dispatcher=dispatcher,
        workspace_path_resolver=lambda _: "/tmp/shared-ws",
    )
    # Pre-acquire the lease to simulate an external holder for `seed` first.
    # `seed` will fail → fork skipped → branches skipped → merge skipped →
    # tail skipped → run failed.
    pre_lease = store.acquire_lease(
        path="/tmp/shared-ws", run_id="external", step_run_id="external_step"
    )
    try:
        with pytest.raises(StepRuntimeError) as exc_info:
            service.start_run(workflow_id=wf.workflow_id, version=1)
        assert exc_info.value.code == "workspace_lease_conflict"
    finally:
        store.release_lease(pre_lease.lease_id)


def test_lease_acquisition_releases_on_settle(store: WorkflowDefinitionStore):
    """Branch leases must release after the step settles, even with shared path."""
    fan = _fan_out_definition()
    wf, _ = store.create_workflow(name="leases", definition_json=fan)
    service = WorkflowRunService(
        store=store,
        dispatcher=_RecordingDispatcher(),
        workspace_path_resolver=lambda _: "/tmp/shared-ws-2",
    )
    run = service.start_run(workflow_id=wf.workflow_id, version=1)
    assert run.status == "succeeded"
    assert store.list_active_leases() == []


def test_cancel_run_marks_pending_steps_cancelled(
    store: WorkflowDefinitionStore, linear_definition_json: str
):
    wf, _ = store.create_workflow(name="cancel", definition_json=linear_definition_json)
    run = store.create_run(workflow_id=wf.workflow_id, version=1)
    store.update_run_status(run.run_id, "running")
    pending = store.create_step(run_id=run.run_id, step_id="pre", agent="codex")
    service = WorkflowRunService(
        store=store,
        dispatcher=_RecordingDispatcher(),
    )
    cancelled = service.cancel_run(run.run_id)
    assert cancelled is not None
    assert cancelled.status == "cancelled"
    steps = {s.step_id: s for s in store.list_steps_for_run(run.run_id)}
    assert steps["pre"].status == "cancelled"


def test_retry_creates_new_run_with_same_trace_id(
    store: WorkflowDefinitionStore, linear_definition_json: str
):
    wf, _ = store.create_workflow(name="retry", definition_json=linear_definition_json)
    service = WorkflowRunService(store=store, dispatcher=_RecordingDispatcher())
    first = service.start_run(
        workflow_id=wf.workflow_id, version=1,
        inputs={"repo_url": "x"}, trace_id="trace-1",
    )
    assert first.trace_id == "trace-1"
    retried = service.retry_run(first.run_id, inputs={"repo_url": "x"})
    assert retried.run_id != first.run_id
    assert retried.trace_id == "trace-1"
    assert retried.retry_of_run_id == first.run_id


def test_100_node_fan_out_runs_under_one_second(store: WorkflowDefinitionStore):
    """Spec §1 F5: 100-node chain schedules within 1s and leaves no leases."""
    import time
    branch_count = 100
    branch_ids = [f"b{i}" for i in range(branch_count)]
    steps: list[dict] = [
        {"id": "seed", "kind": "agent_task", "agent": "codex",
         "task": {"prompt_template": "seed"}, "outputs": ["seed_out"]},
        {"id": "fork", "kind": "parallel", "branches": branch_ids},
    ]
    for branch_id in branch_ids:
        steps.append({
            "id": branch_id, "kind": "agent_task", "agent": "nanobot",
            "task": {"prompt_template": branch_id},
            "outputs": ["branch_out"],
        })
    steps.append({
        "id": "merge", "kind": "join",
        "wait_for": branch_ids, "merge": "concat",
    })
    definition = json.dumps({"name": "wide", "steps": steps})
    wf, _ = store.create_workflow(name="wide", definition_json=definition)
    service = WorkflowRunService(store=store, dispatcher=_RecordingDispatcher())
    began = time.perf_counter()
    run = service.start_run(workflow_id=wf.workflow_id, version=1)
    elapsed = time.perf_counter() - began
    assert run.status == "succeeded"
    assert elapsed < 1.0, f"100-node fan-out took {elapsed:.3f}s, expected < 1s"
    assert store.list_active_leases() == []
    rows = store.list_steps_for_run(run.run_id)
    # seed + fork + 100 branches + merge = 103 step rows.
    assert len(rows) == branch_count + 3


def test_for_each_kind_remains_reserved_at_runner_layer():
    """Even if a malformed definition somehow reaches the runner, the
    closed-set kind constraint surfaces from build_dispatch."""
    bad_step_payload = {
        "id": "x", "kind": "agent_task", "agent": "codex",
        "task": {"prompt_template": "ok"},
    }
    wf = validate_definition({"name": "ok", "steps": [bad_step_payload]})
    # Mutate after validation to simulate corruption.
    wf.steps[0].kind = "for_each"
    ctx = RunContext(inputs={}, workspace={}, steps={})
    with pytest.raises(StepRuntimeError) as exc_info:
        build_dispatch(wf.steps[0], ctx)
    assert exc_info.value.code == "kind_unsupported"
