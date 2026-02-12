from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.quality.confidence import compute_data_confidence, compute_decision_confidence
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse, ToolWarning


@pytest.mark.asyncio
async def test_run_tool_writes_telemetry_events(monkeypatch) -> None:
    from app.bot.services.tool_runner import run_tool

    events: list[tuple[str, dict, str | None]] = []

    async def fake_write(event_type: str, payload: dict, correlation_id: str | None = None) -> None:
        events.append((event_type, payload, correlation_id))

    monkeypatch.setattr("app.bot.services.tool_runner.write_audit_event", fake_write)

    async def handler(payload, correlation_id: str, session) -> ToolResponse:
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={"value": 1},
            provenance=ToolProvenance(sources=["demo"], window={"day": "2026-01-01"}),
            warnings=[ToolWarning(code="INSUFFICIENT_DATA", message="partial")],
        )

    class DummyPayload:
        def __init__(self, **kwargs):
            self.kwargs = kwargs

    tool = SimpleNamespace(name="dummy", payload_model=DummyPayload, handler=handler)
    registry = SimpleNamespace(get=lambda _: tool)

    class DummyScope:
        async def __aenter__(self):
            return None

        async def __aexit__(self, exc_type, exc, tb):
            return False

    response = await run_tool(
        "dummy",
        {},
        actor=ToolActor(owner_user_id=100),
        tenant=SimpleNamespace(),
        correlation_id="corr-obs",
        idempotency_key="idem-1",
        session_factory=lambda: DummyScope(),
        registry=registry,
    )

    assert response.status == "ok"
    assert events[0][0] == "tool_call_started"
    assert events[0][1]["tool"] == "dummy"
    assert events[0][1]["idempotency_key"] == "idem-1"
    assert events[0][1]["actor_id"] == 100
    assert events[1][0] == "tool_call_finished"
    assert events[1][1]["status"] == "ok"
    assert events[1][1]["warnings_count"] == 1
    assert events[1][2] == "corr-obs"


def test_confidence_ok_with_provenance() -> None:
    response = ToolResponse.ok(
        correlation_id="c1",
        data={"kpi": 10},
        provenance=ToolProvenance(sources=["demo"], window={"day": "2026-01-01"}),
    )

    data_conf = compute_data_confidence(response)
    decision_conf = compute_decision_confidence(1.0, data_conf.score, had_errors=False)

    assert data_conf.score >= 0.8
    assert "tool_ok" in data_conf.reasons
    assert decision_conf.score > 0.8


def test_confidence_warning_insufficient_data() -> None:
    response = ToolResponse.ok(
        correlation_id="c2",
        data={"kpi": 10},
        provenance=ToolProvenance(sources=["demo"], window={"day": "2026-01-01"}),
        warnings=[ToolWarning(code="INSUFFICIENT_DATA", message="partial")],
    )

    data_conf = compute_data_confidence(response)
    assert data_conf.score < 0.9
    assert any(reason.startswith("warning:INSUFFICIENT_DATA") for reason in data_conf.reasons)


def test_confidence_error_case() -> None:
    response = ToolResponse.error(correlation_id="c3", code="UPSTREAM_UNAVAILABLE", message="upstream")

    data_conf = compute_data_confidence(response)
    decision_conf = compute_decision_confidence(0.5, data_conf.score, had_errors=True)

    assert data_conf.score == 0.0
    assert decision_conf.score == 0.0
