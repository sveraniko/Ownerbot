from __future__ import annotations

from pathlib import Path

from app.agent_actions.phrase_pack import match_action_phrase
from app.agent_actions.plan_builder import build_plan_from_text


PHRASES = [
    ("Проверь курс", "sis_fx_status"),
    ("Какой сейчас курс?", "sis_fx_status"),
    ("Проверь курс и если надо обнови цены", "plan:sis_fx_reprice_auto"),
    ("Обнови цены по курсу", "sis_fx_reprice_auto"),
    ("Пересчитай цены по курсу", "sis_fx_reprice_auto"),
    ("Сделай репрайс", "sis_fx_reprice_auto"),
    ("Принудительно обнови цены по курсу", "sis_fx_reprice_auto"),
    ("Откатить последнее обновление цен", "sis_fx_rollback"),
    ("Подними цены на 5%", "sis_prices_bump"),
    ("Снизь цены на 3%", "sis_prices_bump"),
    ("Сделай купон -10% на сутки", "plan:create_coupon"),
    ("Сделай скидку 15% на 48 часов", "plan:create_coupon"),
    ("Сделай купон -20% на 7 дней", "plan:create_coupon"),
    ("Выключи купон CODE", "create_coupon"),
    ("Поставь скидку 10% на товары 12,13,14", "sis_discounts_set"),
    ("Убери скидки с товаров 12,13", "sis_discounts_clear"),
    ("Опубликуй товары 12,13", "sis_products_publish"),
    ("Скрой товары 44,45", "sis_products_publish"),
    ("Опубликуй луки 1,2", "sis_looks_publish"),
    ("Скрой луки 7,8", "sis_looks_publish"),
]


def test_rule_pack_contract_20_phrases() -> None:
    for phrase, expected in PHRASES:
        if expected.startswith("plan:"):
            plan = build_plan_from_text(phrase, actor=None, settings=None)
            assert plan is not None, phrase
            tool = expected.split(":", 1)[1]
            assert any(step.tool_name == tool for step in plan.steps), phrase
            continue
        match = match_action_phrase(phrase)
        assert match is not None, phrase
        assert match.tool_name == expected, phrase


def test_phrase_pack_doc_mentions_ssot_path() -> None:
    content = Path("docs/OWNERBOT_ACTION_PHRASE_PACK.md").read_text(encoding="utf-8")
    assert "app/agent_actions/phrase_pack.py" in content
