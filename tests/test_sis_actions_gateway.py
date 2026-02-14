from types import SimpleNamespace

import pytest

from app.tools.providers.sis_actions_gateway import run_sis_action


@pytest.mark.asyncio
async def test_gateway_parses_dict_warnings(monkeypatch) -> None:
    class _Client:
        def __init__(self, settings):
            self.settings = settings

        async def post_action(self, path, payload, correlation_id):
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

        async def post_action(self, path, payload, correlation_id):
            return 200, {"warnings": ["legacy warning"]}

    monkeypatch.setattr("app.tools.providers.sis_actions_gateway.SisActionsClient", _Client)
    response = await run_sis_action(path="/x", payload={}, correlation_id="c2", settings=SimpleNamespace())
    assert response.status == "ok"
    assert response.warnings[0].code == "SIS_WARNING"
    assert response.warnings[0].message == "legacy warning"
