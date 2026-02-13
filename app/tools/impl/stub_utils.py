from __future__ import annotations

from pydantic import BaseModel

from app.tools.contracts import ToolResponse


class StubPayload(BaseModel):
    pass


class ActionStubPayload(BaseModel):
    dry_run: bool = True


def not_implemented(correlation_id: str, tool_name: str) -> ToolResponse:
    return ToolResponse.fail(
        correlation_id=correlation_id,
        code="NOT_IMPLEMENTED",
        message=f"Tool {tool_name} is not implemented yet.",
    )
