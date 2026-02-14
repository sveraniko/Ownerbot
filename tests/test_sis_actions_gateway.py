from types import SimpleNamespace

import pytest

from app.tools.providers.sis_actions_gateway import run_sis_action, run_sis_request


@pytest.mark.asyncio
async def test_gateway_parses_dict_warnings(monkeypatch) -> None:
    class _Client:
        def __init__(self, settings):
            self.settings = settings

        async def post_action(self, path, payload, correlation_id, idempotency_key=None):
            return 200, {"warnings": [{"code": "FORCE_REQUIRED", "message": "Need force"}]}

    monkeypatch.setattr("app.tools.providers.sis_actions_gateway.SisActionsClient", _Client)
    response = await run_sis_action(path="/x", payload={}, correlation_id="c1", settings=SimpleNamespace())
    assert response.status == "ok"
    assert response.warnings[0].code == "FORCE_REQUIRED"
    assert response.warnings[0].message == "Need force"


@pytest.mark.asyncio
async def test_gateway_parses_string_warnings(monkeypatch) -> None:
    class _Client:
        def __init__(self, settings):
            self.settings = settings

        async def post_action(self, path, payload, correlation_id, idempotency_key=None):
            return 200, {"warnings": ["legacy warning"]}

    monkeypatch.setattr("app.tools.providers.sis_actions_gateway.SisActionsClient", _Client)
    response = await run_sis_action(path="/x", payload={}, correlation_id="c2", settings=SimpleNamespace())
    assert response.status == "ok"
    assert response.warnings[0].code == "SIS_WARNING"
    assert response.warnings[0].message == "legacy warning"


@pytest.mark.asyncio
async def test_gateway_parses_envelope_ok(monkeypatch) -> None:
    class _Client:
        def __init__(self, settings):
            self.settings = settings

        async def get_action(self, path, correlation_id):
            return 200, {
                "ok": True,
                "correlation_id": "corr-1",
                "request_hash": "h1",
                "warnings": [{"code": "W1", "message": "warn"}],
                "data": {"value": 10},
            }

    monkeypatch.setattr("app.tools.providers.sis_actions_gateway.SisActionsClient", _Client)
    response = await run_sis_request(method="GET", path="/fx/status", payload=None, correlation_id="c3", settings=SimpleNamespace())
    assert response.status == "ok"
    assert response.data["value"] == 10
    assert response.data["correlation_id"] == "corr-1"
    assert response.data["request_hash"] == "h1"


@pytest.mark.asyncio
async def test_gateway_envelope_error_returns_tool_error(monkeypatch) -> None:
    class _Client:
        def __init__(self, settings):
            self.settings = settings

        async def post_action(self, path, payload, correlation_id, idempotency_key=None):
            return 200, {"ok": False, "error": {"message": "boom"}, "data": {}}

    monkeypatch.setattr("app.tools.providers.sis_actions_gateway.SisActionsClient", _Client)
    response = await run_sis_request(method="POST", path="/fx/apply", payload={}, correlation_id="c4", settings=SimpleNamespace())
    assert response.status == "error"
    assert response.error is not None
    assert response.error.message == "boom"
