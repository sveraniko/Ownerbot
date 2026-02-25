from __future__ import annotations

from types import SimpleNamespace

import pytest

from app.advice.classifier import AdviceTopic
from app.advice.data_brief import DataBriefResult
from app.advice.memo_renderer import render_decision_memo_pdf


class _DummyMessage:
    def __init__(self) -> None:
        self.chat = SimpleNamespace(id=11)
        self.docs = []

    async def answer_document(self, document, caption: str | None = None):
        self.docs.append((document, caption))


class _DummyCallback:
    def __init__(self, data: str) -> None:
        self.data = data
        self.from_user = SimpleNamespace(id=5)
        self.message = _DummyMessage()
        self.answers = []

    async def answer(self, text=None, show_alert=False):
        self.answers.append((text, show_alert))


@pytest.mark.asyncio
async def test_memo_handler_missing_cache_returns_helpful_error(monkeypatch) -> None:
    from app.bot.routers import owner_console

    async def _load_last_advice(chat_id: int):
        del chat_id
        return None

    events = []

    async def _write_audit_event(name: str, payload: dict, correlation_id: str | None = None):
        del correlation_id
        events.append((name, payload))

    monkeypatch.setattr(owner_console, "load_last_advice", _load_last_advice)
    monkeypatch.setattr(owner_console, "write_audit_event", _write_audit_event)

    cb = _DummyCallback(f"{owner_console._ADVICE_MEMO_PREFIX}{AdviceTopic.PRICING_STRATEGY.value}")
    await owner_console.generate_advice_memo(cb)

    assert cb.message.docs == []
    assert cb.answers[-1] == ("Сначала получи совет/бриф", True)
    assert events and events[-1][0] == "advice_memo_failed"


def test_memo_renderer_returns_pdf_bytes_with_ru_text_and_brief_section() -> None:
    brief = DataBriefResult(
        created_at="2026-01-01T00:00:00+00:00",
        topic=AdviceTopic.PRICING_STRATEGY,
        tools_run=[{"tool": "kpi_compare", "ok": True, "warnings_count": 0}],
        facts={"kpi": {"revenue_net_a": 1200, "revenue_net_b": 1000}, "fx": {"base_currency": "EUR", "shop_currency": "RUB", "latest_rate": 93.5, "would_apply": False}},
        summary="Выручка растёт\nМаржа стабильна",
        warnings=[],
    )
    advice_cache = {
        "hypotheses": ["Проверить ценовой коридор на топ-товарах"],
        "risks": ["Риск просадки маржи при резком снижении цен"],
        "experiments": ["A/B тест на 10% ассортимента"],
        "suggested_actions": [{"label": "Подготовить купон", "why": "Проверка эластичности"}],
    }

    pdf_bytes = render_decision_memo_pdf("pricing_strategy", brief, advice_cache)

    assert pdf_bytes
    assert len(pdf_bytes) > 500
    assert b"Data Brief" in pdf_bytes


def test_memo_renderer_without_brief_keeps_facts_section() -> None:
    advice_cache = {
        "hypotheses": ["Сконцентрироваться на SKU с высоким AOV"],
        "risks": ["Недостаточно данных по возвратам"],
        "experiments": ["Сравнить 7/30 дней"],
        "suggested_actions": [],
    }

    pdf_bytes = render_decision_memo_pdf("assortment_strategy", None, advice_cache)

    assert pdf_bytes
    assert b"No brief cached" in pdf_bytes
