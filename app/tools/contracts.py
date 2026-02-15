from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Dict, List, Optional

from pydantic import BaseModel, Field

from app.core.time import utcnow


class ToolActor(BaseModel):
    owner_user_id: int
    role: str = "owner"


class ToolTenant(BaseModel):
    project: str
    shop_id: str
    currency: str
    timezone: str
    locale: str


class ToolRequest(BaseModel):
    tool: str
    version: str = "1.0"
    correlation_id: str
    idempotency_key: str
    actor: ToolActor
    tenant: ToolTenant
    payload: Dict[str, Any]


class ToolWarning(BaseModel):
    code: str
    message: str


class ToolProvenance(BaseModel):
    sources: List[str] = Field(default_factory=list)
    window: Optional[Dict[str, Any]] = None
    filters_hash: Optional[str] = None


class ToolError(BaseModel):
    code: str
    message: str
    details: Optional[Dict[str, Any]] = None


class ToolArtifact(BaseModel):
    type: str
    filename: str
    content: bytes
    caption: str | None = None


class ToolResponse(BaseModel):
    status: str
    correlation_id: str
    as_of: datetime
    data: Dict[str, Any] = Field(default_factory=dict)
    artifacts: List[ToolArtifact] = Field(default_factory=list)
    warnings: List[ToolWarning] = Field(default_factory=list)
    provenance: ToolProvenance = Field(default_factory=ToolProvenance)
    error: Optional[ToolError] = None

    @classmethod
    def ok(
        cls,
        correlation_id: str,
        data: Dict[str, Any],
        provenance: ToolProvenance,
        warnings: Optional[List[ToolWarning]] = None,
        artifacts: Optional[List[ToolArtifact]] = None,
    ) -> "ToolResponse":
        return cls(
            status="ok",
            correlation_id=correlation_id,
            as_of=utcnow(),
            data=data,
            warnings=warnings or [],
            artifacts=artifacts or [],
            provenance=provenance,
        )

    @classmethod
    def fail(
        cls,
        correlation_id: str,
        code: str,
        message: str,
        details: Optional[Dict[str, Any]] = None,
    ) -> "ToolResponse":
        return cls(
            status="error",
            correlation_id=correlation_id,
            as_of=utcnow(),
            error=ToolError(code=code, message=message, details=details),
        )


@dataclass
class ToolDefinition:
    name: str
    version: str
    payload_model: type[BaseModel]
    handler: Any
    is_stub: bool = False
    kind: str = "read"
