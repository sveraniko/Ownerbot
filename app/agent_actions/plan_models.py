from __future__ import annotations

from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class PlanStep(BaseModel):
    step_id: Literal["s1", "s2"]
    kind: Literal["TOOL", "NOTIFY_TEAM"]
    tool_name: str | None = None
    payload: dict[str, Any] | None = None
    requires_confirm: bool = False
    condition: dict[str, str] | None = None

    @field_validator("condition")
    @classmethod
    def _validate_condition(cls, value: dict[str, str] | None) -> dict[str, str] | None:
        if value is None:
            return None
        if value not in ({"if": "would_apply_true"}, {"if": "commit_succeeded"}):
            raise ValueError("Unsupported condition")
        return value


class PlanIntent(BaseModel):
    plan_id: str
    source: Literal["RULE_PHRASE_PACK", "LLM"]
    steps: list[PlanStep] = Field(min_length=1, max_length=2)
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
        if len(self.steps) == 2:
            step2 = self.steps[1]
            if step2.step_id != "s2" or step2.kind != "NOTIFY_TEAM":
                raise ValueError("Step2 must be NOTIFY_TEAM")
            if step2.requires_confirm:
                raise ValueError("Step2 cannot require confirm")
        return self
