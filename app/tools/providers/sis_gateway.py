from __future__ import annotations

from app.tools.contracts import ToolResponse


def upstream_unavailable(correlation_id: str) -> ToolResponse:
    return ToolResponse.error(
        correlation_id=correlation_id,
        code="UPSTREAM_UNAVAILABLE",
        message="SIS upstream is unavailable.",
    )
