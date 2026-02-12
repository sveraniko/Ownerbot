from __future__ import annotations

from dataclasses import dataclass

from app.tools.contracts import ToolResponse


@dataclass
class ConfidenceResult:
    score: float
    reasons: list[str]


def _clamp(value: float) -> float:
    return max(0.0, min(1.0, round(value, 4)))


def compute_data_confidence(response: ToolResponse) -> ConfidenceResult:
    reasons: list[str] = []

    if response.status == "error":
        reasons.append("tool_error")
        if response.error is not None:
            reasons.append(f"error_code:{response.error.code}")
        return ConfidenceResult(score=0.0, reasons=reasons)

    score = 0.9
    if response.warnings:
        score -= 0.2
        reasons.extend([f"warning:{item.code}" for item in response.warnings])

    if not response.provenance.sources:
        score -= 0.3
        reasons.append("missing_provenance_sources")
    if response.provenance.window is None:
        score -= 0.1
        reasons.append("missing_provenance_window")

    reasons.append("tool_ok")
    return ConfidenceResult(score=_clamp(score), reasons=reasons)


def compute_decision_confidence(
    llm_confidence: float,
    data_confidence: float,
    had_errors: bool,
) -> ConfidenceResult:
    reasons: list[str] = []
    if had_errors:
        reasons.append("had_errors")
        return ConfidenceResult(score=0.0, reasons=reasons)

    score = (0.4 * _clamp(llm_confidence)) + (0.6 * _clamp(data_confidence))
    if llm_confidence >= 0.999:
        reasons.append("intent_source:rule")
    else:
        reasons.append("intent_source:llm")
    reasons.append(f"llm_confidence:{_clamp(llm_confidence)}")
    reasons.append(f"data_confidence:{_clamp(data_confidence)}")

    return ConfidenceResult(score=_clamp(score), reasons=reasons)
