from __future__ import annotations

import re
from typing import Any

from app.quality.models import QualityBadge, QualityContext
from app.tools.contracts import ToolResponse

_METRIC_PATTERN = re.compile(r"\b\d+(?:[\.,]\d+)?\s*(?:%|₽|\$|€|k|m|тыс|млн)?\b", re.IGNORECASE)


def _short_warning(value: str) -> str:
    compact = " ".join(value.split())
    if len(compact) <= 120:
        return compact
    return compact[:119] + "…"


def assess_tool_response(tool_resp: ToolResponse, ctx: QualityContext) -> QualityBadge:
    warnings: list[str] = []
    warnings.extend([_short_warning(f"{item.code}: {item.message}") for item in tool_resp.warnings])

    if tool_resp.error and tool_resp.error.code == "UPSTREAM_NOT_IMPLEMENTED":
        warnings.append("Upstream not wired")
    if tool_resp.status == "ok" and not tool_resp.data:
        warnings.append("No data")

    has_provenance = bool(tool_resp.provenance and tool_resp.provenance.sources)

    if tool_resp.status != "ok" or not has_provenance or not tool_resp.data:
        confidence = "low"
    elif warnings or tool_resp.provenance.window is None:
        confidence = "med"
    else:
        confidence = "high"

    if has_provenance:
        provenance = "data"
    elif tool_resp.status == "ok" and tool_resp.data:
        provenance = "mixed"
    else:
        provenance = "hypothesis"

    return QualityBadge(confidence=confidence, provenance=provenance, warnings=warnings)


def assess_advice_intent(advice_payload: Any, ctx: QualityContext) -> QualityBadge:
    confidence_value = float(getattr(advice_payload, "confidence", 0.0) or 0.0)
    if confidence_value >= 0.75:
        confidence = "high"
    elif confidence_value >= 0.45:
        confidence = "med"
    else:
        confidence = "low"

    warnings: list[str] = []
    experiments = list(getattr(advice_payload, "experiments", []) or [])
    suggested_tools = list(getattr(advice_payload, "suggested_tools", []) or [])
    bullets = list(getattr(advice_payload, "bullets", []) or [])
    risks = list(getattr(advice_payload, "risks", []) or [])
    title = str(getattr(advice_payload, "title", "") or "")

    if not experiments:
        warnings.append("No verification plan")
    if not bullets:
        warnings.append("No hypotheses listed")
    if not suggested_tools:
        warnings.append("No data validation tools suggested")
    combined_text = " ".join([title] + bullets + risks + experiments)
    if _METRIC_PATTERN.search(combined_text):
        warnings.append("Possible metrics in advice")

    return QualityBadge(confidence=confidence, provenance="hypothesis", warnings=[_short_warning(item) for item in warnings])


def format_quality_header(badge: QualityBadge) -> str:
    return f"🧭 Качество: {badge.confidence.upper()} | 📌 {badge.provenance.upper()} | ⚠️ {len(badge.warnings)}"
