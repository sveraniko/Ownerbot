from __future__ import annotations

from types import SimpleNamespace

from app.quality.models import QualityContext
from app.quality.verifier import assess_advice_intent


def test_advice_quality_maps_confidence_and_hypothesis() -> None:
    payload = SimpleNamespace(
        confidence=0.8,
        title="Советник",
        bullets=["Это гипотеза: проверить канал трафика"],
        risks=["Ложноположительная связь"],
        experiments=["Сравнить 7д vs 30д"],
        suggested_tools=[{"tool": "kpi_snapshot"}],
    )
    badge = assess_advice_intent(payload, QualityContext(intent_source="LLM", intent_kind="ADVICE"))
    assert badge.confidence == "high"
    assert badge.provenance == "hypothesis"


def test_advice_quality_warns_without_experiments() -> None:
    payload = SimpleNamespace(confidence=0.5, title="Совет", bullets=["Проверить гипотезу"], risks=[], experiments=[], suggested_tools=[{"tool": "kpi_snapshot"}])
    badge = assess_advice_intent(payload, QualityContext(intent_source="LLM", intent_kind="ADVICE"))
    assert "No verification plan" in badge.warnings


def test_advice_quality_warns_on_possible_metrics() -> None:
    payload = SimpleNamespace(confidence=0.4, title="Совет", bullets=["Рост на 20% из-за акции"], risks=[], experiments=["A/B"], suggested_tools=[{"tool": "kpi_snapshot"}])
    badge = assess_advice_intent(payload, QualityContext(intent_source="LLM", intent_kind="ADVICE"))
    assert "Possible metrics in advice" in badge.warnings
