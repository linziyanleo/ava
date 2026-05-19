"""DSL validator for workflow definitions.

Accepted ``step.kind`` closed set:

  v1 (AVA-47 P2a) — ``agent_task``
  v2 (AVA-25 P2b) — ``agent_task`` | ``parallel`` | ``join``

P2b unlocks fan-out / fan-in (all_success only). The reserved-vocabulary table
still names the future tickets that own the remaining kinds.

Reject set (validator raises with the ticket name in the message):

  for_each                     → AVA-25 / P2b (deferred sub-feature)
  conditional / branch         → AVA-31 / P3
  loop / approval / nested     → AVA-31 / P3

Inputs use a JSONPath subset (``$.inputs.*``, ``$.workspace.root``,
``$.steps.<id>.outputs.<name>``). The validator is permissive about exact
JSONPath grammar; the runner enforces resolvability when it dereferences.
"""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


# Reserved keywords that are explicitly NOT allowed; each maps to the Linear
# ticket and milestone where they will land. ``parallel`` and ``join`` were
# released here in P2b (AVA-25) so they no longer appear.
RESERVED_KIND_REJECT: dict[str, tuple[str, str]] = {
    "for_each":    ("AVA-25", "P2b"),
    "conditional": ("AVA-31", "P3"),
    "branch":      ("AVA-31", "P3"),
    "loop":        ("AVA-31", "P3"),
    "approval":    ("AVA-31", "P3"),
    "nested":      ("AVA-31", "P3"),
}

ACCEPTED_STEP_KINDS: frozenset[str] = frozenset({"agent_task", "parallel", "join"})

JOIN_MERGE_STRATEGIES: frozenset[str] = frozenset({"concat", "merge-objects", "last-success"})

LOCAL_AGENTS = {"codex", "claude_code", "image_gen", "nanobot"}
A2A_PREFIX = "a2a://"

_JSONPATH_PATTERN = re.compile(
    r"^\$\.(inputs|workspace|steps)(\.[A-Za-z_][A-Za-z0-9_]*)+$"
)
_STEP_ID_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_AGENT_NAME_PATTERN = re.compile(r"^[A-Za-z_][A-Za-z0-9_-]*$")


class WorkflowInputDecl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    type: Literal["string", "number", "boolean", "object", "array"] = "string"
    description: str = ""
    default: Any = None


class WorkflowOutputDecl(BaseModel):
    model_config = ConfigDict(extra="forbid")
    name: str = Field(min_length=1)
    type: Literal["string", "number", "boolean", "object", "array"] = "string"
    description: str = ""


class StepTaskBlock(BaseModel):
    model_config = ConfigDict(extra="forbid")
    prompt_template: str = Field(min_length=1)
    tools: list[str] = Field(default_factory=list)
    skill: str | None = None


class WorkflowStep(BaseModel):
    """A single executable step. v2 closed set: ``agent_task | parallel | join``."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    # agent_task fields (also reused as join output declaration)
    agent: str | None = None
    task: StepTaskBlock | None = None
    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: list[str] = Field(default_factory=list)
    next: str | None = None
    # parallel fields
    branches: list[str] | None = None
    # join fields
    wait_for: list[str] | None = None
    merge: str | None = None

    @field_validator("id")
    @classmethod
    def _check_id(cls, value: str) -> str:
        if not _STEP_ID_PATTERN.match(value):
            raise ValueError(
                f"step.id '{value}' must match [A-Za-z_][A-Za-z0-9_]*"
            )
        return value

    @field_validator("kind")
    @classmethod
    def _check_kind(cls, value: str) -> str:
        if value in ACCEPTED_STEP_KINDS:
            return value
        if value in RESERVED_KIND_REJECT:
            ticket, phase = RESERVED_KIND_REJECT[value]
            raise ValueError(
                f"step.kind '{value}' is reserved for {ticket} ({phase}); "
                f"current schema accepts {sorted(ACCEPTED_STEP_KINDS)}"
            )
        raise ValueError(
            f"step.kind '{value}' is not a recognised kind; only "
            f"{sorted(ACCEPTED_STEP_KINDS)} are allowed"
        )

    @field_validator("agent")
    @classmethod
    def _check_agent(cls, value: str | None) -> str | None:
        if value is None:
            return value
        if value.startswith(A2A_PREFIX):
            tail = value[len(A2A_PREFIX):]
            if not tail or "/" not in tail:
                raise ValueError(
                    "step.agent 'a2a://' URI must include host/agent path"
                )
            return value
        if value in LOCAL_AGENTS:
            return value
        if not _AGENT_NAME_PATTERN.match(value):
            raise ValueError(
                f"step.agent '{value}' must be one of {sorted(LOCAL_AGENTS)} "
                f"or an 'a2a://host/agent' URI"
            )
        return value

    @field_validator("inputs")
    @classmethod
    def _check_inputs(cls, value: dict[str, str]) -> dict[str, str]:
        for key, expr in value.items():
            if not _STEP_ID_PATTERN.match(key):
                raise ValueError(
                    f"step.inputs key '{key}' must be a valid identifier"
                )
            if not _JSONPATH_PATTERN.match(expr):
                raise ValueError(
                    f"step.inputs['{key}']='{expr}' must be a JSONPath like "
                    f"$.inputs.<name>, $.workspace.<name>, or "
                    f"$.steps.<step_id>.outputs.<name>"
                )
        return value

    @field_validator("outputs")
    @classmethod
    def _check_outputs(cls, value: list[str]) -> list[str]:
        for output in value:
            if not _STEP_ID_PATTERN.match(output):
                raise ValueError(
                    f"step.outputs entry '{output}' must be a valid identifier"
                )
        return value

    @field_validator("merge")
    @classmethod
    def _check_merge(cls, value: str | None) -> str | None:
        if value is None or value in JOIN_MERGE_STRATEGIES:
            return value
        raise ValueError(
            f"join.merge '{value}' must be one of {sorted(JOIN_MERGE_STRATEGIES)}"
        )

    @field_validator("branches")
    @classmethod
    def _check_branches(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        for entry in value:
            if not _STEP_ID_PATTERN.match(entry):
                raise ValueError(
                    f"parallel.branches entry '{entry}' must be a valid step.id"
                )
        return value

    @field_validator("wait_for")
    @classmethod
    def _check_wait_for(cls, value: list[str] | None) -> list[str] | None:
        if value is None:
            return value
        for entry in value:
            if not _STEP_ID_PATTERN.match(entry):
                raise ValueError(
                    f"join.wait_for entry '{entry}' must be a valid step.id"
                )
        return value

    @model_validator(mode="after")
    def _check_per_kind(self) -> WorkflowStep:
        if self.kind == "agent_task":
            if self.agent is None:
                raise ValueError(f"agent_task step '{self.id}' must declare agent")
            if self.task is None:
                raise ValueError(f"agent_task step '{self.id}' must declare task")
            if self.branches is not None or self.wait_for is not None or self.merge is not None:
                raise ValueError(
                    f"agent_task step '{self.id}' must not declare branches / wait_for / merge"
                )
        elif self.kind == "parallel":
            if not self.branches:
                raise ValueError(
                    f"parallel step '{self.id}' must declare non-empty branches"
                )
            if self.task is not None or self.agent is not None:
                raise ValueError(
                    f"parallel step '{self.id}' must not declare agent / task"
                )
            if self.inputs or self.outputs:
                raise ValueError(
                    f"parallel step '{self.id}' must not declare inputs / outputs"
                )
            if self.wait_for is not None or self.merge is not None:
                raise ValueError(
                    f"parallel step '{self.id}' must not declare wait_for / merge"
                )
            if len(set(self.branches)) != len(self.branches):
                raise ValueError(
                    f"parallel step '{self.id}' branches must be unique"
                )
        elif self.kind == "join":
            if not self.wait_for:
                raise ValueError(
                    f"join step '{self.id}' must declare non-empty wait_for"
                )
            if self.merge is None:
                raise ValueError(
                    f"join step '{self.id}' must declare merge strategy "
                    f"({sorted(JOIN_MERGE_STRATEGIES)})"
                )
            if self.task is not None or self.agent is not None:
                raise ValueError(
                    f"join step '{self.id}' must not declare agent / task"
                )
            if self.inputs or self.branches is not None:
                raise ValueError(
                    f"join step '{self.id}' must not declare inputs / branches"
                )
            if len(set(self.wait_for)) != len(self.wait_for):
                raise ValueError(
                    f"join step '{self.id}' wait_for must be unique"
                )
            if self.id in self.wait_for:
                raise ValueError(f"join step '{self.id}' cannot wait for itself")
        return self


class WorkflowDefinition(BaseModel):
    """Top-level workflow definition document (DSL v2)."""

    model_config = ConfigDict(extra="forbid")

    workflow_id: str = Field(default="", description="Empty when authoring a draft")
    version: int = Field(default=1, ge=1)
    name: str = Field(min_length=1)
    description: str = ""
    inputs: list[WorkflowInputDecl] = Field(default_factory=list)
    outputs: list[WorkflowOutputDecl] = Field(default_factory=list)
    steps: list[WorkflowStep] = Field(min_length=1)

    @model_validator(mode="after")
    def _check_chain(self) -> WorkflowDefinition:
        seen_ids: set[str] = set()
        for step in self.steps:
            if step.id in seen_ids:
                raise ValueError(f"duplicate step.id '{step.id}'")
            seen_ids.add(step.id)
        # `next` must reference a known step or be None (linear default).
        for step in self.steps:
            if step.next is not None and step.next not in seen_ids:
                raise ValueError(
                    f"step '{step.id}' next='{step.next}' references unknown step"
                )
        # Cross-step references for parallel/join must target known step ids.
        # parallel.branches must be downstream (positions after self) so that the
        # runner dispatches them as fan-out children. join.wait_for must be
        # upstream so the dependency is satisfiable without cycles.
        ordered_ids: list[str] = [step.id for step in self.steps]
        position: dict[str, int] = {step_id: idx for idx, step_id in enumerate(ordered_ids)}
        for index, step in enumerate(self.steps):
            allowed_upstream = set(ordered_ids[:index])
            allowed_downstream = set(ordered_ids[index + 1:])
            if step.kind == "parallel":
                for branch_id in step.branches or []:
                    if branch_id not in seen_ids:
                        raise ValueError(
                            f"parallel step '{step.id}' branches reference "
                            f"unknown step '{branch_id}'"
                        )
                    if branch_id == step.id:
                        raise ValueError(
                            f"parallel step '{step.id}' cannot branch to itself"
                        )
                    if branch_id not in allowed_downstream:
                        raise ValueError(
                            f"parallel step '{step.id}' branch '{branch_id}' "
                            f"must be a downstream step (after position {index})"
                        )
            elif step.kind == "join":
                for upstream_id in step.wait_for or []:
                    if upstream_id not in seen_ids:
                        raise ValueError(
                            f"join step '{step.id}' wait_for references "
                            f"unknown step '{upstream_id}'"
                        )
                    if upstream_id not in allowed_upstream:
                        raise ValueError(
                            f"join step '{step.id}' wait_for '{upstream_id}' "
                            f"must be an upstream step (before position {index})"
                        )
            for key, expr in step.inputs.items():
                if expr.startswith("$.steps."):
                    parts = expr.split(".")
                    if len(parts) < 4:
                        raise ValueError(
                            f"step '{step.id}' inputs['{key}']='{expr}' is malformed"
                        )
                    upstream = parts[2]
                    if upstream == step.id:
                        raise ValueError(
                            f"step '{step.id}' cannot reference its own outputs"
                        )
                    if upstream not in allowed_upstream:
                        raise ValueError(
                            f"step '{step.id}' inputs['{key}'] references "
                            f"downstream/unknown step '{upstream}'"
                        )
        return self


def validate_definition(payload: dict[str, Any]) -> WorkflowDefinition:
    """Validate a raw dict payload against the current DSL.

    Raises pydantic.ValidationError when invalid; returns the parsed model
    on success.
    """
    return WorkflowDefinition.model_validate(payload)


def is_a2a_agent(agent: str | None) -> bool:
    """True if the agent URI is ``a2a://...`` (runner must fail-fast)."""
    return bool(agent) and agent.startswith(A2A_PREFIX)


__all__ = [
    "A2A_PREFIX",
    "ACCEPTED_STEP_KINDS",
    "JOIN_MERGE_STRATEGIES",
    "LOCAL_AGENTS",
    "RESERVED_KIND_REJECT",
    "StepTaskBlock",
    "WorkflowDefinition",
    "WorkflowInputDecl",
    "WorkflowOutputDecl",
    "WorkflowStep",
    "ValidationError",
    "is_a2a_agent",
    "validate_definition",
]
