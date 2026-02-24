from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from app.notify.digest_builder import build_daily_digest


@pytest.mark.asyncio
async def test_build_daily_digest_graceful_degradation(monkeypatch, fixed_time_utc) -> None:
    monkeypatch.setattr("app.notify.digest_builder.kpi_compare.handle", AsyncMock(return_value=SimpleNamespace(status="error", data={})))
    monkeypatch.setattr("app.notify.digest_builder.revenue_trend.handle", AsyncMock(return_value=SimpleNamespace(status="ok", data={"series": []})))
    monkeypatch.setattr("app.notify.digest_builder.chats_unanswered.handle", AsyncMock(return_value=SimpleNamespace(status="error", data={})))
    monkeypatch.setattr("app.notify.digest_builder.sys_last_errors.handle", AsyncMock(return_value=SimpleNamespace(status="ok", data={"count": 0})))
    monkeypatch.setattr("app.notify.digest_builder.sis_fx_status.handle", AsyncMock(return_value=SimpleNamespace(status="error", data={})))
    monkeypatch.setattr("app.notify.digest_builder.orders_search.handle", AsyncMock(return_value=SimpleNamespace(status="error", data={})))
    monkeypatch.setattr("app.notify.digest_builder.inventory_status.handle", AsyncMock(return_value=SimpleNamespace(status="error", data={})))

    bundle = await build_daily_digest(1, session=object(), correlation_id="cid")
    assert bundle.text
    assert "Сводка за" in bundle.text
    assert bundle.warnings
