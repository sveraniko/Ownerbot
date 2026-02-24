from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field


class QualityBadge(BaseModel):
    confidence: Literal["high", "med", "low"]
    provenance: Literal["data", "hypothesis", "mixed"]
    warnings: list[str] = Field(default_factory=list)


class QualityContext(BaseModel):
    intent_source: Literal["RULE", "LLM", "TEMPLATE"]
    intent_kind: Literal["TOOL", "ADVICE", "UNKNOWN"] | None = None
    tool_name: str | None = None
