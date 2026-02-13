from __future__ import annotations

from typing import Any

from app.tools.contracts import ToolResponse


def _has_numeric(value: Any) -> bool:
    if isinstance(value, (int, float)):
        return True
    if isinstance(value, dict):
        return any(_has_numeric(v) for v in value.values())
    if isinstance(value, list):
        return any(_has_numeric(v) for v in value)
    return False


def verify_response(response: ToolResponse) -> ToolResponse:
    if response.status == "error":
        return response

    if _has_numeric(response.data):
        if not response.provenance.sources:
            return ToolResponse.fail(
                correlation_id=response.correlation_id,
                code="PROVENANCE_MISSING",
                message="Numeric KPI requires provenance sources.",
            )
        if response.provenance.window is None:
            return ToolResponse.fail(
                correlation_id=response.correlation_id,
                code="PROVENANCE_INCOMPLETE",
                message="Numeric KPI requires provenance window.",
            )
        if response.as_of is None:
            return ToolResponse.fail(
                correlation_id=response.correlation_id,
                code="PROVENANCE_INCOMPLETE",
                message="Numeric KPI requires as_of.",
            )

    return response
