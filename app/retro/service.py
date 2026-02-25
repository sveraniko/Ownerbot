from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.time import utcnow
from app.storage.models import OwnerbotAuditEvent

_ALLOWED_PERIODS = {7, 30}
_UNKNOWN_REASON_CODES = {
    "MISSING_PARAMETERS": "missing_params",
    "VALIDATION_ERROR": "invalid_payload",
    "NO_TOOL": "no_match",
    "UPSTREAM_NOT_IMPLEMENTED": "upstream_not_implemented",
}


@dataclass
class RetroSummary:
    period_days: int
    totals: dict[str, int]
    routing: dict[str, float]
    top_tools: list[dict[str, int | str]]
    quality: dict[str, object]
    failures: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


@dataclass
class RetroGaps:
    period_days: int
    top_unimplemented_tools: list[dict[str, int | str]]
    top_disallowed_actions: list[dict[str, int | str]]
    top_missing_params: list[dict[str, int | str]]

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _validate_period_days(period_days: int) -> None:
    if period_days not in _ALLOWED_PERIODS:
        raise ValueError("period_days must be 7 or 30")


def _parse_payload(raw_payload: str) -> dict[str, object]:
    try:
        parsed = json.loads(raw_payload)
    except json.JSONDecodeError:
        return {}
    return parsed if isinstance(parsed, dict) else {}


async def _load_event_rows(session: AsyncSession, period_days: int) -> list[tuple[str, str]]:
    _validate_period_days(period_days)
    start_at = utcnow() - timedelta(days=period_days)
    stmt = (
        select(OwnerbotAuditEvent.event_type, OwnerbotAuditEvent.payload_json)
        .where(OwnerbotAuditEvent.occurred_at >= start_at)
        .where(
            OwnerbotAuditEvent.event_type.in_(
                [
                    "llm_intent_planned",
                    "quality_assessment",
                    "tool_call_started",
                    "tool_call_finished",
                    "agent_plan_previewed_v2",
                    "agent_plan_committed_v2",
                    "advice_memo_generated",
                    "advice_data_brief_built",
                    "llm_intent_failed",
                    "agent_action_wizard_started",
                ]
            )
        )
    )
    result = await session.execute(stmt)
    return list(result.all())


async def retro_summary(session: AsyncSession, period_days: int) -> RetroSummary:
    rows = await _load_event_rows(session, period_days)

    event_counts: Counter[str] = Counter()
    rule_hits_total = 0
    llm_plans_total = 0
    tool_counts: Counter[str] = Counter()
    quality_confidence_counts: dict[str, Counter[str]] = {"TOOL": Counter(), "ADVICE": Counter()}
    warning_counts: Counter[str] = Counter()
    unknown_reasons: Counter[str] = Counter()

    for event_type, payload_json in rows:
        event_counts[event_type] += 1
        payload = _parse_payload(payload_json)

        if event_type == "quality_assessment":
            source = str(payload.get("intent_source") or "").upper()
            if source == "RULE":
                rule_hits_total += 1
            intent_kind = str(payload.get("intent_kind") or "").upper()
            confidence = str(payload.get("confidence") or "").lower()
            if intent_kind in {"TOOL", "ADVICE"} and confidence in {"high", "med", "low"}:
                quality_confidence_counts[intent_kind][confidence] += 1
            for warning in list(payload.get("top_warning_codes") or []):
                if isinstance(warning, str) and warning:
                    warning_counts[warning] += 1

        if event_type == "llm_intent_planned":
            llm_plans_total += 1

        if event_type == "tool_call_started":
            tool_name = str(payload.get("tool") or "").strip()
            if tool_name:
                tool_counts[tool_name] += 1

        if event_type == "llm_intent_failed":
            unknown_reasons[_UNKNOWN_REASON_CODES.get(str(payload.get("error_class") or ""), "no_match")] += 1

        if event_type == "tool_call_finished":
            error_code = str(payload.get("error_code") or "")
            mapped_reason = _UNKNOWN_REASON_CODES.get(error_code)
            if mapped_reason:
                unknown_reasons[mapped_reason] += 1

    intents_total = rule_hits_total + llm_plans_total
    totals = {
        "intents_total": intents_total,
        "advice_total": quality_confidence_counts["ADVICE"].total(),
        "tool_calls_total": event_counts["tool_call_started"],
        "plans_previewed_total": event_counts["agent_plan_previewed_v2"],
        "plans_committed_total": event_counts["agent_plan_committed_v2"],
        "memos_generated_total": event_counts["advice_memo_generated"],
        "briefs_built_total": event_counts["advice_data_brief_built"],
    }

    routing = {
        "rule_hits_total": rule_hits_total,
        "llm_plans_total": llm_plans_total,
        "llm_fallback_rate": round(llm_plans_total / max(1, intents_total), 4),
    }

    top_tools = [
        {"tool_name": tool_name, "count": count}
        for tool_name, count in tool_counts.most_common(5)
    ]

    quality = {
        "confidence_counts": {
            "TOOL": {
                "high": quality_confidence_counts["TOOL"]["high"],
                "med": quality_confidence_counts["TOOL"]["med"],
                "low": quality_confidence_counts["TOOL"]["low"],
            },
            "ADVICE": {
                "high": quality_confidence_counts["ADVICE"]["high"],
                "med": quality_confidence_counts["ADVICE"]["med"],
                "low": quality_confidence_counts["ADVICE"]["low"],
            },
        },
        "top_warning_codes": [{"warning": warning, "count": count} for warning, count in warning_counts.most_common(5)],
    }

    failures = {
        "unknown_total": sum(unknown_reasons.values()),
        "top_unknown_reasons": [{"reason": reason, "count": count} for reason, count in unknown_reasons.most_common(5)],
    }

    return RetroSummary(
        period_days=period_days,
        totals=totals,
        routing=routing,
        top_tools=top_tools,
        quality=quality,
        failures=failures,
    )


async def retro_gaps(session: AsyncSession, period_days: int) -> RetroGaps:
    rows = await _load_event_rows(session, period_days)

    unimplemented_tools: Counter[str] = Counter()
    disallowed_actions: Counter[str] = Counter()
    missing_params: Counter[str] = Counter()

    for event_type, payload_json in rows:
        payload = _parse_payload(payload_json)

        if event_type == "tool_call_finished":
            error_code = str(payload.get("error_code") or "")
            tool_name = str(payload.get("tool") or "unknown")
            if error_code == "UPSTREAM_NOT_IMPLEMENTED":
                unimplemented_tools[tool_name] += 1
            if error_code == "ACTION_TOOL_NOT_ALLOWED":
                disallowed_actions[tool_name] += 1

        if event_type == "agent_action_wizard_started":
            for field_name in list(payload.get("missing_fields") or []):
                if isinstance(field_name, str) and field_name:
                    missing_params[field_name] += 1

    return RetroGaps(
        period_days=period_days,
        top_unimplemented_tools=[{"tool_name": tool_name, "count": count} for tool_name, count in unimplemented_tools.most_common(5)],
        top_disallowed_actions=[{"tool_name": tool_name, "count": count} for tool_name, count in disallowed_actions.most_common(5)],
        top_missing_params=[{"param": key, "count": count} for key, count in missing_params.most_common(5)],
    )
