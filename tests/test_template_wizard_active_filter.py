from types import SimpleNamespace

import pytest

from app.bot.filters.template_wizard_active import TemplateWizardActive


class _RedisStub:
    def __init__(self, payload: str | None) -> None:
        self.payload = payload

    async def get(self, key: str):
        return self.payload


@pytest.mark.asyncio
async def test_template_wizard_active_no_state(monkeypatch) -> None:
    from app.bot.filters import template_wizard_active as mod

    async def _get_redis():
        return _RedisStub(None)

    monkeypatch.setattr(mod, "get_redis", _get_redis)

    filt = TemplateWizardActive()
    message = SimpleNamespace(text="42", from_user=SimpleNamespace(id=7))

    assert await filt(message) is False


@pytest.mark.asyncio
async def test_template_wizard_active_with_state(monkeypatch) -> None:
    from app.bot.filters import template_wizard_active as mod

    async def _get_redis():
        return _RedisStub('{"template_id":"PRC_BUMP","step_index":0}')

    monkeypatch.setattr(mod, "get_redis", _get_redis)

    filt = TemplateWizardActive()
    message = SimpleNamespace(text="10", from_user=SimpleNamespace(id=7))

    assert await filt(message) == {"tpl_state": {"template_id": "PRC_BUMP", "step_index": 0}}


@pytest.mark.asyncio
async def test_template_wizard_active_ignores_command_with_state(monkeypatch) -> None:
    from app.bot.filters import template_wizard_active as mod

    async def _get_redis():
        return _RedisStub('{"template_id":"PRC_BUMP","step_index":0}')

    monkeypatch.setattr(mod, "get_redis", _get_redis)

    filt = TemplateWizardActive()
    message = SimpleNamespace(text="/systems", from_user=SimpleNamespace(id=7))

    assert await filt(message) is False
