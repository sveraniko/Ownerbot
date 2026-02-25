from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, model_validator


class AdviceSuggestedTool(BaseModel):
    tool: str
    payload: dict = Field(default_factory=dict)
    why: str = ""


class AdviceSuggestedAction(BaseModel):
    label: str
    plan_hint: str | None = None
    tool: str | None = None
    payload_partial: dict = Field(default_factory=dict)
    why: str = ""


class AdvicePayload(BaseModel):
    title: str = ""
    bullets: list[str] = Field(default_factory=list)
    risks: list[str] = Field(default_factory=list)
    experiments: list[str] = Field(default_factory=list)
    suggested_tools: list[AdviceSuggestedTool] = Field(default_factory=list)
    suggested_actions: list[AdviceSuggestedAction] = Field(default_factory=list)


class LLMIntent(BaseModel):
    intent_kind: Literal["TOOL", "ADVICE", "UNKNOWN"] = "UNKNOWN"
    tool: str | None = None
    payload: dict = Field(default_factory=dict)
    presentation: dict | None = None
    advice: AdvicePayload | None = None
    error_message: str | None = None
    confidence: float = 0.0
    tool_source: Literal["LLM", "RULE"] | None = None
    tool_kind: Literal["action", "report"] | None = None

    @model_validator(mode="after")
    def _validate_consistency(self) -> "LLMIntent":
        if self.intent_kind == "TOOL":
            if not self.tool:
                raise ValueError("TOOL intent requires tool")
        elif self.intent_kind == "ADVICE":
            if self.advice is None:
                raise ValueError("ADVICE intent requires advice payload")
        elif self.intent_kind == "UNKNOWN":
            if not self.error_message:
                raise ValueError("UNKNOWN intent requires error_message")
        return self
