from app.advice.classifier import AdviceTopic, classify_advice_topic


def test_classifier_maps_ru_keywords() -> None:
    assert classify_advice_topic("что будет популярно весна-лето") == AdviceTopic.SEASON_TRENDS
    assert classify_advice_topic("какую акцию и купон сделать") == AdviceTopic.PROMO_STRATEGY
    assert classify_advice_topic("что делать с ценами, дорого") == AdviceTopic.PRICING_STRATEGY
    assert classify_advice_topic("что чистить в ассортименте каталога") == AdviceTopic.ASSORTMENT_STRATEGY
    assert classify_advice_topic("что горит в операционке у команды") == AdviceTopic.OPS_PRIORITY
