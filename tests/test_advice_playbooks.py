from app.advice.classifier import AdviceTopic
from app.advice.playbooks import build_playbook


def test_playbooks_have_required_sections() -> None:
    topics = [
        AdviceTopic.SEASON_TRENDS,
        AdviceTopic.PROMO_STRATEGY,
        AdviceTopic.PRICING_STRATEGY,
        AdviceTopic.ASSORTMENT_STRATEGY,
        AdviceTopic.OPS_PRIORITY,
        AdviceTopic.GROWTH_PLAN,
    ]
    for topic in topics:
        result = build_playbook(topic, preset_id=topic.value)
        assert result is not None
        assert result.advice.title
        assert result.advice.bullets
        assert result.advice.experiments
        assert result.advice.suggested_tools
        assert result.advice.suggested_actions
