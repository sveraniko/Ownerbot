from __future__ import annotations

from dataclasses import dataclass

from app.advice.classifier import AdviceTopic
from app.llm.schema import AdvicePayload, AdviceSuggestedAction, AdviceSuggestedTool


@dataclass
class AdvicePlaybookResult:
    topic: AdviceTopic
    preset_id: str
    advice: AdvicePayload


def _base_hypothesis_note() -> str:
    return "Это гипотезы, без внешнего ресерча: проверяем только вашими внутренними данными."


def build_playbook(topic: AdviceTopic, *, preset_id: str) -> AdvicePlaybookResult | None:
    if topic == AdviceTopic.SEASON_TRENDS:
        advice = AdvicePayload(
            title="Весна–лето: что качать в продажах",
            bullets=[
                _base_hypothesis_note(),
                "Вероятен сдвиг спроса в лёгкие и базовые категории; проверьте рост доли категории.",
                "Сезонные SKU могут расти быстрее при наличии полного размера/остатка.",
                "Категории с низкой маржой лучше поддерживать акцией, а не ранним репрайсом.",
            ],
            risks=["Риск перезаказа сезонки без подтверждения спроса.", "Риск каннибализации базовых товаров скидками."],
            experiments=[
                "Сравнить top_categories за 30d и 7d, чтобы увидеть ускорение сезонных категорий.",
                "Проверить revenue_trend и top_products по сезонным SKU против базы.",
                "Сверить inventory_status: не продвигать товары с низким остатком.",
                "Проверить demand_forecast по ключевым категориям на 2–4 недели.",
            ],
            suggested_tools=[
                AdviceSuggestedTool(tool="top_products", payload={"window": "30d", "group_by": "category"}),
                AdviceSuggestedTool(tool="revenue_trend", payload={"days": 30}),
                AdviceSuggestedTool(tool="inventory_status", payload={}),
                AdviceSuggestedTool(tool="demand_forecast", payload={"days": 28}),
            ],
            suggested_actions=[
                AdviceSuggestedAction(
                    label="Сделать мягкий репрайс сезонных позиций (preview)",
                    tool="sis_prices_bump",
                    payload_partial={"dry_run": True, "value": 5},
                    why="Проверить, даст ли небольшая корректировка цены положительный эффект без риска.",
                )
            ],
        )
        return AdvicePlaybookResult(topic=topic, preset_id=preset_id, advice=advice)

    if topic == AdviceTopic.PROMO_STRATEGY:
        advice = AdvicePayload(
            title="Промо сейчас: купон vs репрайс",
            bullets=[
                _base_hypothesis_note(),
                "Купон лучше, когда нужно поднять конверсию без изменения витринной цены.",
                "Репрайс лучше, когда нужно перезапустить спрос на полке и ускорить оборачиваемость.",
                "Для новых клиентов купон часто даёт чище измеримый результат, чем общий дисконт.",
            ],
            risks=["Чрезмерная скидка может просадить маржу.", "Постоянные акции могут обучить аудиторию ждать скидку."],
            experiments=[
                "Сравнить KPI до/после купона на коротком окне.",
                "Сверить coupons_status и top_used, чтобы не дублировать активные акции.",
                "Сделать dry_run для create_coupon и оценить охват/ограничения.",
            ],
            suggested_tools=[
                AdviceSuggestedTool(tool="kpi_snapshot", payload={"window": "7d"}),
                AdviceSuggestedTool(tool="coupons_status", payload={}),
                AdviceSuggestedTool(tool="coupons_top_used", payload={"window": "30d"}),
            ],
            suggested_actions=[
                AdviceSuggestedAction(
                    label="Подготовить купон -10% на 24ч (preview)",
                    tool="create_coupon",
                    payload_partial={"dry_run": True, "percent_off": 10, "hours_valid": 24},
                    why="Быстрый тест чувствительности к промо с ограниченным риском.",
                )
            ],
        )
        return AdvicePlaybookResult(topic=topic, preset_id=preset_id, advice=advice)

    if topic == AdviceTopic.PRICING_STRATEGY:
        advice = AdvicePayload(
            title="Стратегия цен: когда менять прайс",
            bullets=[
                _base_hypothesis_note(),
                "Репрайс нужен, когда тренд выручки замедляется и нет дефицита остатков.",
                "Если FX-дельта ниже порогов, частый репрайс создаёт шум без эффекта.",
                "Сначала проверка dry_run, затем только подтверждённый commit.",
            ],
            risks=["Слишком частая смена цен ухудшает предсказуемость спроса."],
            experiments=[
                "Проверить sis_fx_status и preview сценарий через sis_fx_reprice_auto(dry_run=true).",
                "Сопоставить revenue_trend 30d и kpi_compare week-over-week.",
                "Проверить группы товаров с наименьшей оборачиваемостью перед репрайсом.",
            ],
            suggested_tools=[
                AdviceSuggestedTool(tool="sis_fx_status", payload={}),
                AdviceSuggestedTool(tool="revenue_trend", payload={"days": 30}),
                AdviceSuggestedTool(tool="kpi_compare", payload={"window": "wow"}),
            ],
            suggested_actions=[
                AdviceSuggestedAction(
                    label="FX авто-репрайс (preview)",
                    tool="sis_fx_reprice_auto",
                    payload_partial={"dry_run": True, "refresh_snapshot": True},
                    why="Безопасно оценить, есть ли фактическая необходимость обновления цен.",
                )
            ],
        )
        return AdvicePlaybookResult(topic=topic, preset_id=preset_id, advice=advice)

    if topic == AdviceTopic.ASSORTMENT_STRATEGY:
        advice = AdvicePayload(
            title="Ассортимент: что держать, что чистить",
            bullets=[
                _base_hypothesis_note(),
                "Убирайте из фокуса позиции без продаж и с низким контент-качеством карточки.",
                "Поддерживайте в приоритете SKU с устойчивым вкладом в выручку и нормальным остатком.",
                "Перед чисткой проверьте риск потери трафика от длинного хвоста.",
            ],
            risks=["Агрессивная чистка может ухудшить ассортиментную глубину."],
            experiments=[
                "Проверить top_products за 30d и inventory_status.",
                "Собрать список без фото/цены как кандидатов на доработку или архив.",
                "Сделать dry_run публикации/архива для ограниченного набора SKU.",
            ],
            suggested_tools=[
                AdviceSuggestedTool(tool="top_products", payload={"window": "30d"}),
                AdviceSuggestedTool(tool="inventory_status", payload={}),
            ],
            suggested_actions=[
                AdviceSuggestedAction(
                    label="Подготовить изменение цен для медленных SKU (preview)",
                    tool="sis_prices_bump",
                    payload_partial={"dry_run": True, "value": -5},
                    why="Проверить гипотезу ускорения продаж по хвосту ассортимента.",
                )
            ],
        )
        return AdvicePlaybookResult(topic=topic, preset_id=preset_id, advice=advice)

    if topic == AdviceTopic.OPS_PRIORITY:
        advice = AdvicePayload(
            title="Операционка: что чинить первым",
            bullets=[
                _base_hypothesis_note(),
                "Сначала устраняем узкие места в оплатах и неотвеченных чатах.",
                "Вторым приоритетом — зависшие заказы и SLA команды.",
                "Третьим — системные ошибки и повторяющиеся варнинги.",
            ],
            risks=["Фокус только на одном узле может скрыть второй критичный источник потерь."],
            experiments=[
                "Проверить orders_search preset=stuck и chats_unanswered.",
                "Сверить team_queue_summary по очереди и нагрузке.",
                "Просмотреть sys_last_errors на повторяемость причин.",
            ],
            suggested_tools=[
                AdviceSuggestedTool(tool="orders_search", payload={"preset": "stuck", "limit": 20}),
                AdviceSuggestedTool(tool="chats_unanswered", payload={"hours": 2}),
                AdviceSuggestedTool(tool="team_queue_summary", payload={}),
                AdviceSuggestedTool(tool="sys_last_errors", payload={}),
            ],
            suggested_actions=[
                AdviceSuggestedAction(
                    label="Пинг команды по приоритету (preview)",
                    tool="notify_team",
                    payload_partial={"dry_run": True, "message": "Проверьте зависшие заказы и чаты без ответа"},
                    why="Синхронизировать реакцию команды до commit-действий.",
                )
            ],
        )
        return AdvicePlaybookResult(topic=topic, preset_id=preset_id, advice=advice)

    if topic == AdviceTopic.GROWTH_PLAN:
        advice = AdvicePayload(
            title="Лёгкий growth-план на ближайший цикл",
            bullets=[
                _base_hypothesis_note(),
                "Рост проще получить через связку: ассортимент + цена + промо + SLA.",
                "Запускайте короткие циклы проверки гипотез и фиксируйте winner-паттерны.",
                "Сначала подтверждаем данные, затем включаем изменения с confirm.",
            ],
            risks=["Параллельный запуск многих инициатив затруднит атрибуцию эффекта."],
            experiments=[
                "Собрать baseline KPI 7d и 30d.",
                "Выбрать 1 промо и 1 ценовой эксперимент в dry_run.",
                "Проверить ops-узкие места перед масштабированием.",
            ],
            suggested_tools=[
                AdviceSuggestedTool(tool="kpi_snapshot", payload={"window": "7d"}),
                AdviceSuggestedTool(tool="revenue_trend", payload={"days": 30}),
                AdviceSuggestedTool(tool="team_queue_summary", payload={}),
            ],
            suggested_actions=[
                AdviceSuggestedAction(
                    label="Подготовить купон для growth-теста (preview)",
                    tool="create_coupon",
                    payload_partial={"dry_run": True, "percent_off": 10, "hours_valid": 48},
                    why="Низкорисковый стартовый тест на конверсию.",
                )
            ],
        )
        return AdvicePlaybookResult(topic=topic, preset_id=preset_id, advice=advice)

    return None
