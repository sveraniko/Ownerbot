from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

_ALLOWED_CONDITIONS = (
    {"if": "would_apply_true"},
    {"if": "noop_true"},
    {"if": "commit_succeeded"},
    {"if": "always"},
)


class PlanStep(BaseModel):
    step_id: str
    kind: Literal["TOOL", "NOTIFY_TEAM"]
    tool_name: str | None = None
    payload: dict[str, Any] | None = None
    requires_confirm: bool = False
    condition: dict[str, str] | None = None
    label: str | None = None

    @field_validator("step_id")
    @classmethod
    def _validate_step_id(cls, value: str) -> str:
        if value not in {"s1", "s2", "s3", "s4", "s5"}:
            raise ValueError("step_id must be one of s1..s5")
        return value

    @field_validator("condition")
    @classmethod
    def _validate_condition(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return None
        if value not in _ALLOWED_CONDITIONS:
            raise ValueError("Unsupported condition")
        return value


class PlanIntent(BaseModel):
    plan_id: str
    source: Literal["RULE_PHRASE_PACK", "LLM"]
    steps: list[PlanStep] = Field(min_length=1, max_length=5)
    summary: str
    confidence: float | None = None

    @model_validator(mode="after")
    def _validate_steps(self) -> "PlanIntent":
        confirm_steps = [step for step in self.steps if step.requires_confirm]
        if len(confirm_steps) > 1:
            raise ValueError("Only one step may require confirm")
        if self.steps[0].step_id != "s1":
            raise ValueError("First step must be s1")
        if self.steps[0].kind != "TOOL":
            raise ValueError("Step1 must be TOOL")

        expected_ids = [f"s{idx}" for idx in range(1, len(self.steps) + 1)]
        current_ids = [step.step_id for step in self.steps]
        if current_ids != expected_ids:
            raise ValueError("Steps must be ordered and contiguous from s1")

        if confirm_steps and confirm_steps[0].kind != "TOOL":
            raise ValueError("Confirm-required step must be TOOL")
        return self
