from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.diagnostics import diff as diff_module
from app.diagnostics.systems import DiagnosticsContext, format_systems_report, run_systems_check
from app.tools.contracts import ToolProvenance, ToolResponse


def test_normalize_payload_rounds_ignores_and_sorts() -> None:
    payload = {
        "as_of": "2026-01-01T00:00:00Z",
        "totals": {"revenue": 10.456, "filters_hash": "abc"},
        "items": [{"id": 2, "value": 3.333}, {"id": 1, "value": 2.221}],
    }

    normalized = diff_module.normalize_payload(payload)

    assert "as_of" not in normalized
    assert normalized["totals"]["revenue"] == 10.46
    assert normalized["items"][0]["id"] == 1
    assert normalized["items"][1]["value"] == 3.33


def test_format_systems_report_ok() -> None:
    from app.diagnostics.systems import SystemsReport

    report = SystemsReport(
        db_ok=True,
        redis_ok=True,
        effective_mode="DEMO",
        runtime_override=None,
        configured_mode="DEMO",
        sis_status="ok",
        sis_latency_ms=12,
        sis_contract_ok=True,
        sizebot_status="disabled",
    )

    text = format_systems_report(report)
    assert "OwnerBot: DB ✅ / Redis ✅" in text
    assert "SIS runtime: ping ✅ latency=12ms, contract=OK" in text


@pytest.mark.asyncio
async def test_run_systems_check_sis_unavailable(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _ok() -> bool:
        return True

    async def _mode(**kwargs):
        return "DEMO", None

    async def _audit(*args, **kwargs):
        return None

    class _SisClient:
        async def ping(self, correlation_id: str) -> ToolResponse:
            return ToolResponse.fail(correlation_id=correlation_id, code="UPSTREAM_UNAVAILABLE", message="down")

    monkeypatch.setattr("app.diagnostics.systems.check_db", _ok)
    monkeypatch.setattr("app.diagnostics.systems.check_redis", _ok)
    monkeypatch.setattr("app.diagnostics.systems.resolve_effective_mode", _mode)
    monkeypatch.setattr("app.diagnostics.systems._safe_audit", _audit)

    settings = SimpleNamespace(
        upstream_mode="DEMO",
        sis_base_url="https://sis.local",
        sis_contract_check_enabled=True,
        sizebot_check_enabled=False,
        sizebot_base_url="",
        asr_provider="mock",
        asr_convert_voice_ogg_to_wav=True,
        asr_max_seconds=180,
        asr_max_bytes=20000000,
        asr_timeout_sec=20,
        openai_api_key="",
        llm_provider="OFF",
        llm_timeout_seconds=20,
        llm_allowed_action_tools=["notify_team"],
        sis_ownerbot_api_key="",
        sizebot_api_key="",
    )
    report = await run_systems_check(
        DiagnosticsContext(settings=settings, redis=None, correlation_id="corr-1", sis_client=_SisClient())
    )

    assert report.db_ok is True
    assert report.redis_ok is True
    assert report.sis_status == "unavailable"
    assert report.sis_error_code == "UPSTREAM_UNAVAILABLE"


@pytest.mark.asyncio
async def test_run_systems_check_contract_degraded(monkeypatch: pytest.MonkeyPatch) -> None:
    async def _ok() -> bool:
        return True

    async def _mode(**kwargs):
        return "SIS_HTTP", "SIS_HTTP"

    async def _audit(*args, **kwargs):
        return None

    class _SisClient:
        async def ping(self, correlation_id: str) -> ToolResponse:
            return ToolResponse.ok(correlation_id=correlation_id, data={"service": "sis"}, provenance=ToolProvenance())

        async def kpi_summary(self, **kwargs) -> ToolResponse:
            return ToolResponse.fail(correlation_id="corr-1", code="PROVENANCE_INCOMPLETE", message="bad")

    monkeypatch.setattr("app.diagnostics.systems.check_db", _ok)
    monkeypatch.setattr("app.diagnostics.systems.check_redis", _ok)
    monkeypatch.setattr("app.diagnostics.systems.resolve_effective_mode", _mode)
    monkeypatch.setattr("app.diagnostics.systems._safe_audit", _audit)

    settings = SimpleNamespace(
        upstream_mode="AUTO",
        sis_base_url="https://sis.local",
        sis_contract_check_enabled=True,
        sizebot_check_enabled=True,
        sizebot_base_url="",
        asr_provider="mock",
        asr_convert_voice_ogg_to_wav=True,
        asr_max_seconds=180,
        asr_max_bytes=20000000,
        asr_timeout_sec=20,
        openai_api_key="",
        llm_provider="OFF",
        llm_timeout_seconds=20,
        llm_allowed_action_tools=["notify_team"],
        sis_ownerbot_api_key="",
        sizebot_api_key="",
    )
    report = await run_systems_check(
        DiagnosticsContext(settings=settings, redis=None, correlation_id="corr-1", sis_client=_SisClient())
    )

    assert report.sis_status == "degraded"
    assert report.sis_contract_ok is False
    assert report.sizebot_status == "unavailable"
