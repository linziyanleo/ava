"""DSL v1 validator for workflow definitions (AVA-47 P2a).

The schema is a strict closed set:

  step.kind ∈ {"agent_task"}        — ONLY this is allowed at v1
  step.agent ∈ {"codex","claude_code","image_gen","nanobot"} OR "a2a://..."
                                    — schema accepts both; runner rejects
                                      a2a:// with `agent_unsupported` until P3

Reserved vocabulary is defined here so error messages can name the future
issue/phase the user is reaching for. See spec §1 F1 for the table.

Reject set (any of these as step.kind raises a clear validation error):

  parallel / join / for_each   → AVA-25 / P2b
  conditional / branch         → AVA-31 / P3
  loop / approval / nested     → AVA-31 / P3

Inputs use a JSONPath subset (`$.inputs.*`, `$.workspace.root`,
`$.steps.<id>.outputs.<name>`). The validator is permissive about exact
JSONPath grammar; the runner enforces resolvability when it dereferences.
"""
from __future__ import annotations

import re
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, ValidationError, field_validator, model_validator


# Reserved keywords that are explicitly NOT allowed at v1; each maps to the
# Linear ticket and milestone where they will land.
RESERVED_KIND_REJECT: dict[str, tuple[str, str]] = {
    "parallel":    ("AVA-25", "P2b"),
    "join":        ("AVA-25", "P2b"),
    "for_each":    ("AVA-25", "P2b"),
    "conditional": ("AVA-31", "P3"),
    "branch":      ("AVA-31", "P3"),
    "loop":        ("AVA-31", "P3"),
    "approval":    ("AVA-31", "P3"),
    "nested":      ("AVA-31", "P3"),
}

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
    """A single executable step. v1 closed set: kind == 'agent_task' only."""

    model_config = ConfigDict(extra="forbid")

    id: str
    kind: str
    agent: str
    task: StepTaskBlock
    inputs: dict[str, str] = Field(default_factory=dict)
    outputs: list[str] = Field(default_factory=list)
    next: str | None = None

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
        if value == "agent_task":
            return value
        if value in RESERVED_KIND_REJECT:
            ticket, phase = RESERVED_KIND_REJECT[value]
            raise ValueError(
                f"step.kind '{value}' is reserved for {ticket} ({phase}); "
                f"v1 only accepts 'agent_task'"
            )
        raise ValueError(
            f"step.kind '{value}' is not a recognised v1 kind; only "
            f"'agent_task' is allowed at this milestone"
        )

    @field_validator("agent")
    @classmethod
    def _check_agent(cls, value: str) -> str:
        if value.startswith(A2A_PREFIX):
            # forward compat: schema accepts but runner rejects until P3
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
        # accept unknown local-style agent names so future agents register without
        # needing a schema bump; runner still has to know how to route it.
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


class WorkflowDefinition(BaseModel):
    """Top-level workflow definition document (DSL v1)."""

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
        # `inputs` JSONPaths that target other steps must point to upstream ids
        # (linear order). Forward references are rejected.
        ordered_ids: list[str] = [step.id for step in self.steps]
        for index, step in enumerate(self.steps):
            allowed_upstream = set(ordered_ids[:index])
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
    """Validate a raw dict payload against DSL v1.

    Raises pydantic.ValidationError when invalid; returns the parsed model
    on success.
    """
    return WorkflowDefinition.model_validate(payload)


def is_a2a_agent(agent: str) -> bool:
    """True if the agent URI is `a2a://...` (runner must fail-fast)."""
    return agent.startswith(A2A_PREFIX)


__all__ = [
    "A2A_PREFIX",
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
