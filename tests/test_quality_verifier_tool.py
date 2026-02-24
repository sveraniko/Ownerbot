from __future__ import annotations

from app.quality.models import QualityContext
from app.quality.verifier import assess_tool_response
from app.tools.contracts import ToolProvenance, ToolResponse, ToolWarning


def test_tool_quality_ok_with_provenance_is_high_data() -> None:
    response = ToolResponse.ok(
        correlation_id="c1",
        data={"orders": 5},
        provenance=ToolProvenance(sources=["sis:ownerbot/v1/orders/search"], window={"days": 7}),
    )
    badge = assess_tool_response(response, QualityContext(intent_source="RULE", intent_kind="TOOL", tool_name="orders_search"))
    assert badge.confidence == "high"
    assert badge.provenance == "data"


def test_tool_quality_ok_with_warnings_is_med() -> None:
    response = ToolResponse.ok(
        correlation_id="c2",
        data={"orders": 5},
        provenance=ToolProvenance(sources=["sis"], window={"days": 7}),
        warnings=[ToolWarning(code="PARTIAL_DATA", message="partial")],
    )
    badge = assess_tool_response(response, QualityContext(intent_source="RULE", intent_kind="TOOL", tool_name="orders_search"))
    assert badge.confidence == "med"


def test_tool_quality_upstream_not_implemented_is_low_with_warning() -> None:
    response = ToolResponse.fail(correlation_id="c3", code="UPSTREAM_NOT_IMPLEMENTED", message="not wired")
    badge = assess_tool_response(response, QualityContext(intent_source="RULE", intent_kind="TOOL", tool_name="kpi_snapshot"))
    assert badge.confidence == "low"
    assert any("Upstream not wired" in item for item in badge.warnings)


def test_tool_quality_empty_data_is_low() -> None:
    response = ToolResponse.ok(
        correlation_id="c4",
        data={},
        provenance=ToolProvenance(sources=["sis"], window={"days": 7}),
    )
    badge = assess_tool_response(response, QualityContext(intent_source="RULE", intent_kind="TOOL", tool_name="kpi_snapshot"))
    assert badge.confidence == "low"
    assert any("No data" in item for item in badge.warnings)
