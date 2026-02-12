from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.bot.ui.formatting import format_tool_response
from app.core.redis import InMemoryRedis
from app.tools.contracts import ToolProvenance, ToolResponse
from app.upstream.mode_store import get_runtime_mode, set_runtime_mode
from app.upstream.selector import choose_data_mode, resolve_effective_mode
from app.upstream.sis_client import _parse_envelope


@pytest.mark.asyncio
async def test_runtime_toggle_store_redis_like() -> None:
    redis = InMemoryRedis()
    await set_runtime_mode(redis, "ownerbot:upstream_mode", "sis_http")
    mode = await get_runtime_mode(redis, "ownerbot:upstream_mode")
    assert mode == "SIS_HTTP"


@pytest.mark.asyncio
async def test_effective_mode_resolution() -> None:
    redis = InMemoryRedis()
    settings = SimpleNamespace(upstream_runtime_toggle_enabled=True, upstream_redis_key="ownerbot:upstream_mode", upstream_mode="DEMO")

    mode, runtime = await resolve_effective_mode(settings=settings, redis=redis)
    assert mode == "DEMO"
    assert runtime is None

    await set_runtime_mode(redis, "ownerbot:upstream_mode", "AUTO")
    mode, runtime = await resolve_effective_mode(settings=settings, redis=redis)
    assert mode == "AUTO"
    assert runtime == "AUTO"


def test_sis_check_parses_envelope() -> None:
    envelope = {
        "as_of": "2026-01-01T00:00:00Z",
        "data": {"ok": True, "service": "sis", "gateway": "ownerbot"},
        "provenance": {"sources": ["sis:ownerbot/v1/ping"], "window": None, "filters_hash": "abc"},
    }

    response = _parse_envelope(envelope, correlation_id="corr-1")
    assert response.status == "ok"
    assert response.provenance.filters_hash == "abc"


@pytest.mark.asyncio
async def test_auto_mode_falls_back_to_demo_on_ping_fail() -> None:
    redis = InMemoryRedis()

    async def ping_fail() -> ToolResponse:
        return ToolResponse.error(correlation_id="c1", code="UPSTREAM_UNAVAILABLE", message="down")

    selected_mode, ping_response = await choose_data_mode(
        effective_mode="AUTO",
        redis=redis,
        correlation_id="c1",
        ping_callable=ping_fail,
    )

    assert selected_mode == "DEMO"
    assert ping_response is not None
    assert ping_response.status == "error"


def test_source_tag_in_response_formatter() -> None:
    response = ToolResponse.ok(
        correlation_id="corr-2",
        data={"orders": 10},
        provenance=ToolProvenance(sources=["sis:ownerbot/v1/orders/search"], window={"days": 1}, filters_hash="h1"),
    )
    text = format_tool_response(response)
    assert "Источник: SIS(ownerbot/v1)" in text
