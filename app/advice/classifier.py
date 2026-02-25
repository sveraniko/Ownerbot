from __future__ import annotations

from enum import Enum


class AdviceTopic(str, Enum):
    SEASON_TRENDS = "SEASON_TRENDS"
    PROMO_STRATEGY = "PROMO_STRATEGY"
    PRICING_STRATEGY = "PRICING_STRATEGY"
    ASSORTMENT_STRATEGY = "ASSORTMENT_STRATEGY"
    OPS_PRIORITY = "OPS_PRIORITY"
    GROWTH_PLAN = "GROWTH_PLAN"
    NONE = "NONE"


_KEYWORDS: list[tuple[AdviceTopic, tuple[str, ...]]] = [
    (AdviceTopic.SEASON_TRENDS, ("сезон", "весна", "лето", "тренд", "категори")),
    (AdviceTopic.PROMO_STRATEGY, ("акци", "купон", "скидк", "промо")),
    (AdviceTopic.PRICING_STRATEGY, ("цен", "прайсинг", "дорого", "дешево", "дёшево")),
    (AdviceTopic.ASSORTMENT_STRATEGY, ("ассортимент", "каталог", "убрать товар", "убрать товары", "чистить каталог")),
    (AdviceTopic.OPS_PRIORITY, ("что горит", "операционк", "команда")),
    (AdviceTopic.GROWTH_PLAN, ("рост", "масштаб", "growth", "план роста")),
]


def classify_advice_topic(text: str) -> AdviceTopic:
    lowered = text.lower()
    for topic, keywords in _KEYWORDS:
        if any(word in lowered for word in keywords):
            return topic
    return AdviceTopic.NONE
