from types import SimpleNamespace

import pytest

from app.actions.capabilities import (
    capability_support_status,
    get_sis_capabilities,
)
from app.core.redis import get_test_redis
from app.tools.providers.sis_actions_gateway import run_sis_action


@pytest.mark.asyncio
async def test_probe_status_mapping(monkeypatch) -> None:
    await get_test_redis()

    class _Client:
        def __init__(self, settings):
            self.settings = settings

        async def get_action(self, path, correlation_id):
            return 401, {}

        async def post_action(self, path, payload, correlation_id, idempotency_key=None):
            by_path = {
                "/prices/bump/preview": 404,
                "/reprice/rollback/preview": 422,
                "/discounts/set/preview": 0,
                "/products/publish/preview": 200,
                "/looks/publish/preview": 403,
            }
            return by_path[path], {}

        async def patch_action(self, path, payload, correlation_id):
            return 200, {}

    monkeypatch.setattr("app.actions.capabilities.SisActionsClient", _Client)

    settings = SimpleNamespace(upstream_mode="SIS_HTTP", sis_base_url="http://sis")
    report = await get_sis_capabilities(settings=settings, correlation_id="cap-1", force_refresh=True)

    assert capability_support_status(report, "prices_bump") is False
    assert capability_support_status(report, "prices_rollback") is True
    assert capability_support_status(report, "discounts") is None
    assert report["capabilities"]["looks_publish"]["status"] == "misconfigured"


@pytest.mark.asyncio
async def test_capabilities_cache_reuses_previous_probe(monkeypatch) -> None:
    redis = await get_test_redis()
    redis._store.clear()
    redis._expiry.clear()
    calls = {"count": 0}

    class _Client:
        def __init__(self, settings):
            self.settings = settings

        async def get_action(self, path, correlation_id):
            calls["count"] += 1
            return 200, {}

        async def post_action(self, path, payload, correlation_id, idempotency_key=None):
            calls["count"] += 1
            return 200, {}

        async def patch_action(self, path, payload, correlation_id):
            calls["count"] += 1
            return 200, {}

    monkeypatch.setattr("app.actions.capabilities.SisActionsClient", _Client)
    monkeypatch.setattr("app.actions.capabilities.get_redis", lambda: get_test_redis())

    settings = SimpleNamespace(upstream_mode="SIS_HTTP", sis_base_url="http://sis")
    await get_sis_capabilities(settings=settings, correlation_id="cap-2", force_refresh=True)
    first = calls["count"]
    await get_sis_capabilities(settings=settings, correlation_id="cap-3", force_refresh=False)
    assert calls["count"] == first


@pytest.mark.asyncio
async def test_gateway_blocks_unsupported_capability_without_calling_upstream(monkeypatch) -> None:
    await get_test_redis()

    async def _caps(*, settings, correlation_id, payload_scope=None, force_refresh=False):
        return {
            "checked_at": "2026-01-01T00:00:00+00:00",
            "capabilities": {
                "prices_bump": {"supported": False, "status_code": 404, "endpoint": "/prices/bump/preview"}
            },
        }

    class _Client:
        def __init__(self, settings):
            raise AssertionError("SisActionsClient must not be created when capability unsupported")

    monkeypatch.setattr("app.tools.providers.sis_actions_gateway.get_sis_capabilities", _caps)
    monkeypatch.setattr("app.tools.providers.sis_actions_gateway.SisActionsClient", _Client)

    settings = SimpleNamespace(upstream_mode="SIS_HTTP", sis_base_url="http://sis")
    response = await run_sis_action(
        path="/prices/bump/apply",
        payload={"actor_tg_id": 1},
        correlation_id="cap-4",
        settings=settings,
    )

    assert response.status == "error"
    assert response.error is not None
    assert response.error.code == "UPSTREAM_NOT_IMPLEMENTED"
