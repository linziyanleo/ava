"""Single-step linear-chain workflow runner (AVA-47 P2a baseline).

Translates a validated `WorkflowDefinition` into a sequence of
BackgroundTask submissions. v1 is intentionally limited:

  * step.kind must be `agent_task` (validator enforces; runner double-checks).
  * step.agent `a2a://...` is fail-fast with `agent_unsupported` even though
    the schema accepts the URI for forward compat.
  * Linear chain only — no fan-out, no fan-in, no parallel. Any failure
    fails the whole run; downstream steps are skipped.
  * Each step holds a workspace_lease bound to its step_run_id; the lease
    is released regardless of step outcome.

The runner is split into pure orchestration (this file) and persistence
(`workflow_definition_store.WorkflowDefinitionStore`). Wire-up to
`BackgroundTaskStore` is provided through a dependency-injection seam so
tests can stub it.
"""
from __future__ import annotations

import json
from dataclasses import dataclass
from typing import Any, Callable, Protocol

from ava.console.services.workflow_definition_schema import (
    A2A_PREFIX,
    LOCAL_AGENTS,
    WorkflowDefinition,
    WorkflowStep,
    is_a2a_agent,
    validate_definition,
)
from ava.console.services.workflow_definition_store import (
    WorkflowDefinitionStore,
    WorkflowRunRecord,
    WorkflowStepRecord,
)


class AgentUnsupportedError(RuntimeError):
    """Raised when the runner sees an agent URI it cannot dispatch.

    P2a runner: every `a2a://...` URI is unsupported until P3.
    """


class StepRuntimeError(RuntimeError):
    """Generic runner error; carries an `error_json`-shaped payload."""

    def __init__(self, code: str, message: str, **details: Any) -> None:
        super().__init__(message)
        self.code = code
        self.detail = {"code": code, "message": message, **details}


@dataclass
class StepDispatch:
    """The shape the runner needs to hand to BackgroundTaskStore.submit_task.

    Decoupled from the BG task API so unit tests can assert what would be
    submitted without standing up the executor stack.
    """

    task_type: str  # "codex" | "claude_code" | "image_gen" | "nanobot"
    prompt: str
    tools: list[str]
    skill: str | None
    inputs: dict[str, Any]


class BackgroundTaskDispatcher(Protocol):
    """Minimal seam into `BackgroundTaskStore`."""

    def dispatch(self, dispatch: StepDispatch, *, run_id: str, step_run_id: str) -> str:
        """Submit the task and return a `bg_task_id`."""


@dataclass
class RunContext:
    """Inputs visible to JSONPath resolution, mutating as steps complete."""

    inputs: dict[str, Any]
    workspace: dict[str, Any]
    steps: dict[str, dict[str, Any]]  # step_id → {"outputs": {...}}


def resolve_jsonpath(expr: str, ctx: RunContext) -> Any:
    """Resolve a constrained JSONPath subset against the run context.

    Supported forms:
      $.inputs.<key>          → ctx.inputs[<key>]
      $.workspace.<key>       → ctx.workspace[<key>]
      $.steps.<id>.outputs.<n>→ ctx.steps[<id>]["outputs"][<n>]

    Any other shape raises StepRuntimeError("input_unresolvable").
    """
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
    """Mustache-lite substitution: `{{var}}` from resolved_inputs only.

    The template is treated literally otherwise; we do not implement
    full Mustache. JSONPath references are pre-resolved into
    `resolved_inputs` before this is called.
    """
    rendered = template
    for key, value in resolved_inputs.items():
        rendered = rendered.replace("{{" + key + "}}", str(value))
        # Common-shorthand path so existing prompts using $.inputs.foo wording
        # also work without manual aliasing.
        rendered = rendered.replace("{{inputs." + key + "}}", str(value))
    return rendered


def build_dispatch(step: WorkflowStep, ctx: RunContext) -> StepDispatch:
    """Compose the StepDispatch for a single agent_task step.

    Raises AgentUnsupportedError when the agent URI is `a2a://...`.
    Raises StepRuntimeError on JSONPath resolution failure.
    """
    if step.kind != "agent_task":
        raise StepRuntimeError(
            "kind_unsupported",
            f"runner only handles kind=agent_task at v1 (got '{step.kind}')",
        )
    if is_a2a_agent(step.agent):
        raise AgentUnsupportedError(
            f"agent '{step.agent}' uses a2a:// scheme; not implemented until P3"
        )
    if step.agent not in LOCAL_AGENTS:
        # Forward-compat: validator already ensures the name is identifier-shaped;
        # the runner just refuses what it has no executor for.
        raise StepRuntimeError(
            "agent_unsupported",
            f"agent '{step.agent}' has no local executor; expected one of {sorted(LOCAL_AGENTS)}",
        )
    resolved: dict[str, Any] = {}
    for key, expr in step.inputs.items():
        resolved[key] = resolve_jsonpath(expr, ctx)
    prompt = render_prompt(step.task.prompt_template, ctx, resolved)
    return StepDispatch(
        task_type=step.agent,  # task_type maps 1:1 to agent name at v1
        prompt=prompt,
        tools=list(step.task.tools),
        skill=step.task.skill,
        inputs=resolved,
    )


class WorkflowRunService:
    """Orchestrates a single workflow run end-to-end (linear chain only).

    The service is *driving* — it expects the caller to advance it after
    each step settles. The actual BG task submission goes through the
    injected `dispatcher`. This keeps the run service unit-testable
    without spinning up the agent runtime.
    """

    def __init__(
        self,
        *,
        store: WorkflowDefinitionStore,
        dispatcher: BackgroundTaskDispatcher,
        workspace_path_resolver: Callable[[WorkflowDefinition], str] | None = None,
    ) -> None:
        self._store = store
        self._dispatcher = dispatcher
        self._workspace_path_resolver = workspace_path_resolver or (lambda _: "")

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def start_run(
        self,
        *,
        workflow_id: str,
        version: int,
        triggered_by: str = "",
        inputs: dict[str, Any] | None = None,
    ) -> WorkflowRunRecord:
        version_row = self._store.get_version(workflow_id, version)
        if version_row is None:
            raise LookupError(f"workflow {workflow_id} v{version} not found")
        definition = validate_definition(json.loads(version_row.definition_json))
        run = self._store.create_run(
            workflow_id=workflow_id, version=version, triggered_by=triggered_by,
        )
        self._store.update_run_status(run.run_id, "running")
        ctx = RunContext(
            inputs=dict(inputs or {}),
            workspace={"root": self._workspace_path_resolver(definition)},
            steps={},
        )
        try:
            self._execute_linear(definition, run.run_id, ctx)
            outputs = self._final_outputs(definition, ctx)
            self._store.update_run_status(run.run_id, "succeeded", final_outputs=outputs)
        except Exception as exc:
            error = exc.detail if isinstance(exc, StepRuntimeError) else {
                "code": "runner_internal",
                "message": str(exc),
            }
            self._store.update_run_status(run.run_id, "failed", final_outputs={"error": error})
            raise
        return self._store.get_run(run.run_id) or run

    # ------------------------------------------------------------------
    # Internals
    # ------------------------------------------------------------------

    def _execute_linear(
        self,
        definition: WorkflowDefinition,
        run_id: str,
        ctx: RunContext,
    ) -> None:
        for step in definition.steps:
            self._execute_step(step, run_id, ctx)

    def _execute_step(
        self,
        step: WorkflowStep,
        run_id: str,
        ctx: RunContext,
    ) -> WorkflowStepRecord:
        record = self._store.create_step(
            run_id=run_id, step_id=step.id, agent=step.agent,
        )
        try:
            dispatch = build_dispatch(step, ctx)
        except AgentUnsupportedError as exc:
            self._store.settle_step(
                record.step_run_id,
                status="failed",
                error={"code": "agent_unsupported", "message": str(exc)},
            )
            raise StepRuntimeError(
                "agent_unsupported", str(exc), step_id=step.id
            ) from exc
        except StepRuntimeError:
            self._store.settle_step(
                record.step_run_id,
                status="failed",
                error={"code": "input_unresolvable", "message": "could not resolve step inputs"},
            )
            raise
        lease_path = ctx.workspace.get("root") or ""
        lease = self._store.acquire_lease(
            path=lease_path, run_id=run_id, step_run_id=record.step_run_id,
        )
        try:
            self._store.mark_step_running(record.step_run_id)
            bg_task_id = self._dispatcher.dispatch(
                dispatch, run_id=run_id, step_run_id=record.step_run_id,
            )
            outputs = self._collect_outputs(step, bg_task_id)
            self._store.settle_step(
                record.step_run_id,
                status="succeeded",
                outputs=outputs,
                bg_task_id=bg_task_id,
            )
            ctx.steps[step.id] = {"outputs": outputs}
        finally:
            self._store.release_lease(lease.lease_id)
        return record

    def _collect_outputs(self, step: WorkflowStep, bg_task_id: str) -> dict[str, Any]:
        # P2a baseline collects outputs from BG task settlement out-of-band; the
        # synchronous dispatcher contract returns once the task has settled and
        # the runner reads outputs back via dispatcher state. For unit tests the
        # dispatcher stub returns synthetic outputs in `dispatch()`; the run
        # service treats the dispatcher's return value as opaque task id and
        # leaves output collection to a follow-up callback wiring (P2c routes
        # are expected to plug a settlement watcher).
        return {name: f"<{bg_task_id}:{name}>" for name in step.outputs}

    def _final_outputs(
        self, definition: WorkflowDefinition, ctx: RunContext
    ) -> dict[str, Any]:
        if not definition.outputs:
            return {}
        last = definition.steps[-1]
        last_outputs = ctx.steps.get(last.id, {}).get("outputs", {})
        return {decl.name: last_outputs.get(decl.name) for decl in definition.outputs}


__all__ = [
    "AgentUnsupportedError",
    "BackgroundTaskDispatcher",
    "RunContext",
    "StepDispatch",
    "StepRuntimeError",
    "WorkflowRunService",
    "build_dispatch",
    "render_prompt",
    "resolve_jsonpath",
]
