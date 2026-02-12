from __future__ import annotations

from pydantic import BaseModel, Field


class LLMIntent(BaseModel):
    tool: str | None = None
    payload: dict = Field(default_factory=dict)
    presentation: dict | None = None
    error_message: str | None = None
    confidence: float = 0.0
