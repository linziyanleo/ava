"""Workflow runner — DAG with fan-out / fan-in (AVA-47 P2a + AVA-25 P2b).

The runner walks a validated ``WorkflowDefinition`` through a small set of
state transitions. v2 closed set is ``{agent_task, parallel, join}``:

  * ``agent_task`` — translates to a ``BackgroundTask`` submission via the
    injected ``BackgroundTaskDispatcher``. ``a2a://...`` agents fail-fast
    until P3.
  * ``parallel``   — routing node; succeeded the moment its predecessors
    succeed. Its branches inherit ``parent_step_id`` pointing at the
    parallel's ``step_run_id`` so the UI can collapse fan-out groups.
  * ``join``       — waits for ``wait_for`` to settle. ``all_success`` only:
    any failed / cancelled / skipped upstream skips the join. The merge
    strategy ``concat | merge-objects | last-success`` (closed set) shapes
    the join's outputs.

Cancel / retry semantics match Linear AVA-25:

  * cancel: pending steps → cancelled, run status → cancelled.
  * retry : creates a new run row (new run_id) with the same trace_id and
    a ``retry_of_run_id`` pointer.

Each step holds its own ``workspace_lease`` bound to its ``step_run_id``;
P2b enforces single-active-lease per non-empty path so fan-out branches
sharing a workspace fail-fast (D4 in the P2b spec).
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Iterable, Protocol

from ava.console.services.workflow_definition_schema import (
    A2A_PREFIX,
    JOIN_MERGE_STRATEGIES,
    LOCAL_AGENTS,
    WorkflowDefinition,
    WorkflowStep,
    is_a2a_agent,
    validate_definition,
)
from ava.console.services.workflow_definition_store import (
    LeaseAcquisitionError,
    WorkflowDefinitionStore,
    WorkflowRunRecord,
    WorkflowStepRecord,
)


# Step status values the runner produces. Mirrors workflow_steps.status text.
PENDING = "pending"
RUNNING = "running"
SUCCEEDED = "succeeded"
FAILED = "failed"
CANCELLED = "cancelled"
SKIPPED = "skipped"

TERMINAL_STATES = frozenset({SUCCEEDED, FAILED, CANCELLED, SKIPPED})
SUCCESS_STATES = frozenset({SUCCEEDED})
NEGATIVE_STATES = frozenset({FAILED, CANCELLED, SKIPPED})


class AgentUnsupportedError(RuntimeError):
    """Raised when the runner sees an agent URI it cannot dispatch."""


class StepRuntimeError(RuntimeError):
    """Generic runner error; carries an ``error_json``-shaped payload."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.detail = {"code": code, "message": message, **details}


@dataclass
class StepDispatch:
    """The shape the runner needs to hand to BackgroundTaskStore.submit_task."""

    task_type: str  # "codex" | "claude_code" | "image_gen" | "nanobot"
    prompt: str
    tools: list[str]
    skill: str | None
    inputs: dict[str, Any]


class BackgroundTaskDispatcher(Protocol):
    """Minimal seam into ``BackgroundTaskStore``."""

    def dispatch(self, dispatch: StepDispatch, *, run_id: str, step_run_id: str) -> str:
        """Submit the task and return a ``bg_task_id``."""


@dataclass
class RunContext:
    """Inputs visible to JSONPath resolution, mutating as steps complete."""

    inputs: dict[str, Any]
    workspace: dict[str, Any]
    steps: dict[str, dict[str, Any]]  # step_id → {"outputs": {...}}


# ---------------------------------------------------------------------------
# JSONPath + prompt helpers (unchanged from P2a)


def resolve_jsonpath(expr: str, ctx: RunContext) -> Any:
    """Resolve a constrained JSONPath subset against the run context."""
    if not expr.startswith("$."):
        raise StepRuntimeError("input_unresolvable", f"unsupported JSONPath: {expr}")
    parts = expr[2:].split(".")
    head, tail = parts[0], parts[1:]
    if head == "inputs":
        if len(tail) != 1:
            raise StepRuntimeError("input_unresolvable", f"$.inputs needs exactly one key: {expr}")
        try:
            return ctx.inputs[tail[0]]
        except KeyError:
            raise StepRuntimeError("input_unresolvable", f"missing $.inputs.{tail[0]}", path=expr)
    if head == "workspace":
        if len(tail) != 1:
            raise StepRuntimeError("input_unresolvable", f"$.workspace needs exactly one key: {expr}")
        try:
            return ctx.workspace[tail[0]]
        except KeyError:
            raise StepRuntimeError("input_unresolvable", f"missing $.workspace.{tail[0]}", path=expr)
    if head == "steps":
        if len(tail) != 3 or tail[1] != "outputs":
            raise StepRuntimeError(
                "input_unresolvable",
                f"$.steps must be $.steps.<id>.outputs.<name>: {expr}",
            )
        step_id, _, output_name = tail
        step_state = ctx.steps.get(step_id)
        if step_state is None:
            raise StepRuntimeError(
                "input_unresolvable",
                f"step '{step_id}' has not produced outputs (path {expr})",
                path=expr,
            )
        outputs = step_state.get("outputs") or {}
        if output_name not in outputs:
            raise StepRuntimeError(
                "input_unresolvable",
                f"step '{step_id}' did not emit output '{output_name}'",
                path=expr,
            )
        return outputs[output_name]
    raise StepRuntimeError("input_unresolvable", f"unsupported JSONPath head: {head}")


def render_prompt(template: str, ctx: RunContext, resolved_inputs: dict[str, Any]) -> str:
    """Mustache-lite substitution: ``{{var}}`` from resolved_inputs only."""
    rendered = template
    for key, value in resolved_inputs.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
        rendered = rendered.replace("{{inputs." + key + "}}", str(value))
    return rendered


def build_dispatch(step: WorkflowStep, ctx: RunContext) -> StepDispatch:
    """Compose the StepDispatch for a single ``agent_task`` step."""
    if step.kind != "agent_task":
        raise StepRuntimeError(
            "kind_unsupported",
            f"build_dispatch only handles kind=agent_task (got '{step.kind}')",
        )
    if is_a2a_agent(step.agent):
        raise AgentUnsupportedError(
            f"agent '{step.agent}' uses a2a:// scheme; not implemented until P3"
        )
    if step.agent not in LOCAL_AGENTS:
        raise StepRuntimeError(
            "agent_unsupported",
            f"agent '{step.agent}' has no local executor; expected one of {sorted(LOCAL_AGENTS)}",
        )
    resolved: dict[str, Any] = {}
    for key, expr in step.inputs.items():
        resolved[key] = resolve_jsonpath(expr, ctx)
    assert step.task is not None  # validator guarantees this for agent_task
    prompt = render_prompt(step.task.prompt_template, ctx, resolved)
    return StepDispatch(
        task_type=step.agent or "",
        prompt=prompt,
        tools=list(step.task.tools),
        skill=step.task.skill,
        inputs=resolved,
    )


# ---------------------------------------------------------------------------
# Predecessor graph


def build_predecessors(definition: WorkflowDefinition) -> dict[str, list[str]]:
    """Compute each step's predecessor list.

    Edges:
      * Default: implicit linear edge from prior array position.
      * parallel.branches: each branch's predecessor is the parallel.
      * join.wait_for: explicit predecessors; no implicit linear edge.
    """
    by_id: dict[str, WorkflowStep] = {step.id: step for step in definition.steps}
    overridden: dict[str, list[str]] = {}
    branch_parent: dict[str, str] = {}
    for step in definition.steps:
        if step.kind == "parallel":
            for branch_id in step.branches or []:
                branch_parent[branch_id] = step.id
        elif step.kind == "join":
            overridden[step.id] = list(step.wait_for or [])
    predecessors: dict[str, list[str]] = {}
    for index, step in enumerate(definition.steps):
        if step.id in overridden:
            predecessors[step.id] = overridden[step.id]
            continue
        if step.id in branch_parent:
            predecessors[step.id] = [branch_parent[step.id]]
            continue
        if index == 0:
            predecessors[step.id] = []
        else:
            predecessors[step.id] = [definition.steps[index - 1].id]
    # Sanity: every referenced predecessor must exist in by_id (validator
    # already enforces this; the dict comprehension below is a guard for
    # future schema changes).
    for step_id, preds in predecessors.items():
        for pred in preds:
            if pred not in by_id:
                raise ValueError(
                    f"runner predecessor '{pred}' for '{step_id}' is not in workflow"
                )
    return predecessors


def branch_parent_map(definition: WorkflowDefinition) -> dict[str, str]:
    """Return {branch_step_id: parallel_step_id} for every fan-out edge."""
    out: dict[str, str] = {}
    for step in definition.steps:
        if step.kind == "parallel":
            for branch_id in step.branches or []:
                out[branch_id] = step.id
    return out


# ---------------------------------------------------------------------------
# Run service


class WorkflowRunService:
    """Orchestrates a workflow run end-to-end.

    Synchronous by design: each step's dispatch returns once the BG task has
    been submitted, and outputs are synthesised from the dispatcher's
    ``bg_task_id`` (P2a contract). True concurrent execution of fan-out
    branches is sequential at the Python level but each branch records its
    own ``step_run_id`` / ``parent_step_id`` so downstream consumers (P2c
    UI, ChainBubble) can render the fan-out group correctly.
    """

    def __init__(
        self,
        *,
        store: WorkflowDefinitionStore,
        dispatcher: BackgroundTaskDispatcher,
        workspace_path_resolver: Callable[[WorkflowDefinition], str] | None = None,
        branch_workspace_resolver: (
            Callable[[WorkflowDefinition, WorkflowStep, str], str] | None
        ) = None,
    ) -> None:
        self._store = store
        self._dispatcher = dispatcher
        self._workspace_path_resolver = workspace_path_resolver or (lambda _: "")
        self._branch_workspace_resolver = branch_workspace_resolver

    # ------------------------------------------------------------------
    # Entry points

    def start_run(
        self,
        *,
        workflow_id: str,
        version: int,
        triggered_by: str = "",
        inputs: dict[str, Any] | None = None,
        trace_id: str = "",
        retry_of_run_id: str = "",
    ) -> WorkflowRunRecord:
        version_row = self._store.get_version(workflow_id, version)
        if version_row is None:
            raise LookupError(f"workflow {workflow_id} v{version} not found")
        definition = validate_definition(json.loads(version_row.definition_json))
        run = self._store.create_run(
            workflow_id=workflow_id,
            version=version,
            triggered_by=triggered_by,
            trace_id=trace_id,
            retry_of_run_id=retry_of_run_id,
        )
        self._store.update_run_status(run.run_id, "running")
        ctx = RunContext(
            inputs=dict(inputs or {}),
            workspace={"root": self._workspace_path_resolver(definition)},
            steps={},
        )
        statuses, first_failure = self._execute_dag(definition, run.run_id, ctx)
        if any(s == FAILED for s in statuses.values()):
            self._store.update_run_status(
                run.run_id,
                "failed",
                final_outputs={
                    "error": (
                        first_failure.detail
                        if first_failure is not None
                        else {"code": "runner_internal", "message": "step failed"}
                    ),
                },
            )
            if first_failure is not None:
                raise first_failure
        else:
            outputs = self._final_outputs(definition, ctx)
            self._store.update_run_status(run.run_id, "succeeded", final_outputs=outputs)
        return self._store.get_run(run.run_id) or run

    def cancel_run(self, run_id: str) -> WorkflowRunRecord | None:
        """Mark all pending steps cancelled and the run cancelled.

        Synchronous runner: by the time the caller reaches us the run is
        either still running on a different thread or already done. We only
        flip pending rows. Callers that own the dispatcher must signal the
        in-flight task themselves (BG task SIGTERM is out-of-scope here).
        """
        run = self._store.get_run(run_id)
        if run is None:
            return None
        steps = self._store.list_steps_for_run(run_id)
        for step in steps:
            if step.status == PENDING:
                self._store.update_step_status(step.step_run_id, CANCELLED)
        if run.status not in {"succeeded", "failed", "cancelled"}:
            self._store.update_run_status(run_id, "cancelled")
        return self._store.get_run(run_id)

    def retry_run(
        self,
        run_id: str,
        *,
        triggered_by: str = "",
        inputs: dict[str, Any] | None = None,
    ) -> WorkflowRunRecord:
        """Create a new run that retains ``trace_id`` and points back via ``retry_of_run_id``.

        Per spec D5 retry creates a fresh chain rather than rerunning the
        existing rows in-place. The new run executes the workflow from the
        top — partial replay of succeeded steps is intentionally out of
        scope at P2b. Callers must re-supply ``inputs`` because the run row
        does not persist them at this milestone.
        """
        prior = self._store.get_run(run_id)
        if prior is None:
            raise LookupError(f"run {run_id} not found")
        return self.start_run(
            workflow_id=prior.workflow_id,
            version=prior.version,
            triggered_by=triggered_by or prior.triggered_by,
            inputs=inputs or {},
            trace_id=prior.trace_id,
            retry_of_run_id=prior.run_id,
        )

    # ------------------------------------------------------------------
    # DAG execution

    def _execute_dag(
        self,
        definition: WorkflowDefinition,
        run_id: str,
        ctx: RunContext,
    ) -> tuple[dict[str, str], StepRuntimeError | None]:
        predecessors = build_predecessors(definition)
        branch_parent = branch_parent_map(definition)
        statuses: dict[str, str] = {step.id: PENDING for step in definition.steps}
        records: dict[str, WorkflowStepRecord] = {}
        first_failure: StepRuntimeError | None = None

        # parent_step_run_id is filled lazily once we execute a parallel.
        parent_step_run_id: dict[str, str] = {}

        def is_branch(step_id: str) -> bool:
            return step_id in branch_parent

        while True:
            if all(statuses[s.id] in TERMINAL_STATES for s in definition.steps):
                break
            progressed = False
            for step in definition.steps:
                if statuses[step.id] != PENDING:
                    continue
                preds = predecessors[step.id]
                pred_statuses = [statuses[p] for p in preds]
                if any(s == PENDING or s == RUNNING for s in pred_statuses):
                    continue  # not yet ready
                # Skip propagation: any predecessor in a non-success terminal
                # state forces this step to skipped.
                if any(s in NEGATIVE_STATES for s in pred_statuses):
                    record = self._store.create_step(
                        run_id=run_id,
                        step_id=step.id,
                        agent=step.agent or "",
                        parent_step_id=parent_step_run_id.get(step.id, ""),
                    )
                    self._store.settle_step(
                        record.step_run_id,
                        status=SKIPPED,
                        error={
                            "code": "predecessor_did_not_succeed",
                            "message": (
                                f"predecessors {preds} did not all succeed"
                            ),
                            "predecessor_statuses": dict(zip(preds, pred_statuses)),
                        },
                    )
                    statuses[step.id] = SKIPPED
                    records[step.id] = record
                    progressed = True
                    continue

                # All preds succeeded — execute step.
                try:
                    if step.kind == "parallel":
                        record = self._execute_parallel(
                            step, run_id,
                            parent_step_run_id.get(step.id, ""),
                        )
                        statuses[step.id] = SUCCEEDED
                        ctx.steps[step.id] = {"outputs": {}}
                        records[step.id] = record
                        # Propagate parent pointer to direct branches.
                        for branch_id in step.branches or []:
                            parent_step_run_id[branch_id] = record.step_run_id
                    elif step.kind == "join":
                        record, outputs = self._execute_join(
                            step, run_id, ctx,
                            parent_step_run_id.get(step.id, ""),
                        )
                        statuses[step.id] = SUCCEEDED
                        ctx.steps[step.id] = {"outputs": outputs}
                        records[step.id] = record
                    else:
                        record = self._execute_agent_task(
                            step, run_id, ctx,
                            parent_step_id=parent_step_run_id.get(step.id, ""),
                        )
                        statuses[step.id] = SUCCEEDED
                        records[step.id] = record
                    progressed = True
                except StepRuntimeError as exc:
                    statuses[step.id] = FAILED
                    if first_failure is None:
                        first_failure = exc
                    progressed = True
                    # If the failure is on a branch, sibling branches and the
                    # join still need to drain — keep looping. For top-level
                    # linear failures the loop will simply mark downstream
                    # steps SKIPPED on the next pass.
                    continue
            if not progressed:
                # Defensive: should not happen with a validated DAG. If it
                # does, mark the rest cancelled and bail out.
                for step in definition.steps:
                    if statuses[step.id] == PENDING:
                        record = self._store.create_step(
                            run_id=run_id,
                            step_id=step.id,
                            agent=step.agent or "",
                            parent_step_id=parent_step_run_id.get(step.id, ""),
                        )
                        self._store.settle_step(
                            record.step_run_id,
                            status=CANCELLED,
                            error={"code": "runner_deadlock", "message": "no progress"},
                        )
                        statuses[step.id] = CANCELLED
                break
        return statuses, first_failure

    def _execute_agent_task(
        self,
        step: WorkflowStep,
        run_id: str,
        ctx: RunContext,
        *,
        parent_step_id: str,
    ) -> WorkflowStepRecord:
        record = self._store.create_step(
            run_id=run_id,
            step_id=step.id,
            agent=step.agent or "",
            parent_step_id=parent_step_id,
        )
        try:
            dispatch = build_dispatch(step, ctx)
        except AgentUnsupportedError as exc:
            self._store.settle_step(
                record.step_run_id,
                status=FAILED,
                error={"code": "agent_unsupported", "message": str(exc)},
            )
            raise StepRuntimeError(
                "agent_unsupported", str(exc), step_id=step.id
            ) from exc
        except StepRuntimeError as exc:
            self._store.settle_step(
                record.step_run_id,
                status=FAILED,
                error=dict(exc.detail, step_id=step.id),
            )
            raise
        lease_path = self._lease_path_for(step, ctx, record.step_run_id)
        try:
            lease = self._store.acquire_lease(
                path=lease_path, run_id=run_id, step_run_id=record.step_run_id,
            )
        except LeaseAcquisitionError as exc:
            self._store.settle_step(
                record.step_run_id,
                status=FAILED,
                error={
                    "code": "workspace_lease_conflict",
                    "message": str(exc),
                    "path": exc.path,
                    "step_id": step.id,
                },
            )
            raise StepRuntimeError(
                "workspace_lease_conflict",
                str(exc),
                step_id=step.id,
                path=exc.path,
            ) from exc
        try:
            self._store.mark_step_running(record.step_run_id)
            bg_task_id = self._dispatcher.dispatch(
                dispatch, run_id=run_id, step_run_id=record.step_run_id,
            )
            outputs = self._collect_outputs(step, bg_task_id)
            self._store.settle_step(
                record.step_run_id,
                status=SUCCEEDED,
                outputs=outputs,
                bg_task_id=bg_task_id,
            )
            ctx.steps[step.id] = {"outputs": outputs}
        finally:
            self._store.release_lease(lease.lease_id)
        return record

    def _execute_parallel(
        self,
        step: WorkflowStep,
        run_id: str,
        parent_step_id: str,
    ) -> WorkflowStepRecord:
        record = self._store.create_step(
            run_id=run_id,
            step_id=step.id,
            agent="",
            parent_step_id=parent_step_id,
        )
        # Parallel is a routing node; no dispatch / no lease.
        self._store.settle_step(
            record.step_run_id,
            status=SUCCEEDED,
            outputs={"branches": list(step.branches or [])},
        )
        return record

    def _execute_join(
        self,
        step: WorkflowStep,
        run_id: str,
        ctx: RunContext,
        parent_step_id: str,
    ) -> tuple[WorkflowStepRecord, dict[str, Any]]:
        record = self._store.create_step(
            run_id=run_id,
            step_id=step.id,
            agent="",
            parent_step_id=parent_step_id,
        )
        upstream_outputs = [
            ctx.steps.get(upstream_id, {}).get("outputs", {})
            for upstream_id in step.wait_for or []
        ]
        outputs = _apply_merge(step.merge or "concat", upstream_outputs)
        self._store.settle_step(
            record.step_run_id,
            status=SUCCEEDED,
            outputs=outputs,
        )
        return record, outputs

    def _lease_path_for(
        self,
        step: WorkflowStep,
        ctx: RunContext,
        step_run_id: str,
    ) -> str:
        """Pick the workspace path for ``step``.

        Branches of a parallel get an isolated path when a
        ``branch_workspace_resolver`` is configured (decision D3). Otherwise
        we fall back to the run-level workspace root (P2a behaviour).
        """
        if self._branch_workspace_resolver is not None:
            try:
                return self._branch_workspace_resolver(
                    None,  # definition unused at this layer; resolver may reuse run state
                    step,
                    step_run_id,
                )
            except TypeError:
                pass
        return ctx.workspace.get("root", "") or ""

    def _collect_outputs(self, step: WorkflowStep, bg_task_id: str) -> dict[str, Any]:
        """Synthesise outputs from the dispatcher's ``bg_task_id``.

        P2a contract: tests stub the dispatcher and treat the run service's
        return value as opaque. P2b inherits this; real output collection
        is a P2c run-monitor concern.
        """
        return {name: f"<{bg_task_id}:{name}>" for name in step.outputs}

    def _final_outputs(
        self, definition: WorkflowDefinition, ctx: RunContext
    ) -> dict[str, Any]:
        if not definition.outputs:
            return {}
        last = definition.steps[-1]
        last_outputs = ctx.steps.get(last.id, {}).get("outputs", {})
        return {decl.name: last_outputs.get(decl.name) for decl in definition.outputs}


# ---------------------------------------------------------------------------
# Merge strategies (closed set frozen by spec)


def _apply_merge(
    strategy: str,
    upstream_outputs: Iterable[dict[str, Any]],
) -> dict[str, Any]:
    """Combine fan-out branch outputs into the join's outputs dict.

    * ``concat``        — group each output name into a list of values.
    * ``merge-objects`` — last-write-wins shallow merge over all branches.
    * ``last-success``  — return the final upstream's outputs verbatim.
    """
    upstream_list = list(upstream_outputs)
    if strategy not in JOIN_MERGE_STRATEGIES:
        raise StepRuntimeError(
            "merge_unsupported",
            f"join.merge '{strategy}' is not in the closed set "
            f"{sorted(JOIN_MERGE_STRATEGIES)}",
        )
    if strategy == "concat":
        result: dict[str, list[Any]] = {}
        for outputs in upstream_list:
            for key, value in outputs.items():
                result.setdefault(key, []).append(value)
        return dict(result)
    if strategy == "merge-objects":
        merged: dict[str, Any] = {}
        for outputs in upstream_list:
            merged.update(outputs)
        return merged
    # last-success
    if not upstream_list:
        return {}
    return dict(upstream_list[-1])


__all__ = [
    "AgentUnsupportedError",
    "BackgroundTaskDispatcher",
    "RunContext",
    "StepDispatch",
    "StepRuntimeError",
    "WorkflowRunService",
    "branch_parent_map",
    "build_dispatch",
    "build_predecessors",
    "render_prompt",
    "resolve_jsonpath",
]
