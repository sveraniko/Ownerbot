from __future__ import annotations

import json
from collections import Counter
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta

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

_SUMMARY_EVENT_TYPES = {
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
}

_GAPS_EVENT_TYPES = {"tool_call_finished", "agent_action_wizard_started"}

_FUNNEL_EVENT_TYPES = {
    "agent_plan_built",
    "agent_plan_previewed",
    "agent_plan_previewed_v2",
    "agent_plan_committed",
    "agent_plan_committed_v2",
    "agent_plan_cancelled",
    "advice_data_brief_requested",
    "advice_data_brief_built",
    "advice_data_brief_cache_hit",
    "advice_playbook_used",
    "advice_generated",
    "advice_actions_suggested",
    "advice_memo_generated",
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


@dataclass
class RetroSummaryWithDeltas:
    current: RetroSummary
    previous: RetroSummary
    deltas: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {"current": self.current.to_dict(), "previous": self.previous.to_dict(), "deltas": self.deltas}


@dataclass
class RetroGapsWithDeltas:
    current: RetroGaps
    previous: RetroGaps
    deltas: dict[str, object]

    def to_dict(self) -> dict[str, object]:
        return {"current": self.current.to_dict(), "previous": self.previous.to_dict(), "deltas": self.deltas}


@dataclass
class FunnelReport:
    period_days: int
    plan: dict[str, object]
    advice: dict[str, object]
    confidence: str
    notes: list[str]

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


def _delta_value(current: int, previous: int) -> dict[str, float | int | None]:
    absolute = current - previous
    percent_change: float | None = None
    if previous > 0:
        percent_change = round((absolute / previous) * 100, 2)
    return {"current": current, "previous": previous, "absolute": absolute, "percent": percent_change}


def _counter_delta(current: Counter[str], previous: Counter[str], key_name: str) -> list[dict[str, float | int | str | None]]:
    diffs: list[dict[str, float | int | str | None]] = []
    for key in sorted(set(current.keys()) | set(previous.keys())):
        metric = _delta_value(current.get(key, 0), previous.get(key, 0))
        if metric["absolute"] == 0:
            continue
        diffs.append({key_name: key, **metric})
    diffs.sort(key=lambda item: abs(int(item["absolute"])), reverse=True)
    return diffs[:5]


async def _query_window(
    session: AsyncSession,
    start_at: datetime,
    end_at: datetime,
    event_types: set[str] | None = None,
) -> list[tuple[str, str, str]]:
    stmt = (
        select(OwnerbotAuditEvent.event_type, OwnerbotAuditEvent.payload_json, OwnerbotAuditEvent.correlation_id)
        .where(OwnerbotAuditEvent.occurred_at >= start_at)
        .where(OwnerbotAuditEvent.occurred_at < end_at)
    )
    if event_types:
        stmt = stmt.where(OwnerbotAuditEvent.event_type.in_(sorted(event_types)))
    result = await session.execute(stmt)
    return list(result.all())


async def _load_event_rows(session: AsyncSession, period_days: int, event_types: set[str]) -> list[tuple[str, str, str]]:
    _validate_period_days(period_days)
    now = utcnow()
    return await _query_window(
        session,
        start_at=now - timedelta(days=period_days),
        end_at=now,
        event_types=event_types,
    )


def _build_summary(rows: list[tuple[str, str, str]], period_days: int) -> RetroSummary:
    event_counts: Counter[str] = Counter()
    rule_hits_total = 0
    llm_plans_total = 0
    tool_counts: Counter[str] = Counter()
    quality_confidence_counts: dict[str, Counter[str]] = {"TOOL": Counter(), "ADVICE": Counter()}
    warning_counts: Counter[str] = Counter()
    unknown_reasons: Counter[str] = Counter()

    for event_type, payload_json, _ in rows:
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

    top_tools = [{"tool_name": tool_name, "count": count} for tool_name, count in tool_counts.most_common(5)]

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

    return RetroSummary(period_days=period_days, totals=totals, routing=routing, top_tools=top_tools, quality=quality, failures=failures)


def _build_gaps(rows: list[tuple[str, str, str]], period_days: int) -> tuple[RetroGaps, Counter[str], Counter[str], Counter[str]]:
    unimplemented_tools: Counter[str] = Counter()
    disallowed_actions: Counter[str] = Counter()
    missing_params: Counter[str] = Counter()

    for event_type, payload_json, _ in rows:
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

    return (
        RetroGaps(
            period_days=period_days,
            top_unimplemented_tools=[{"tool_name": tool_name, "count": count} for tool_name, count in unimplemented_tools.most_common(5)],
            top_disallowed_actions=[{"tool_name": tool_name, "count": count} for tool_name, count in disallowed_actions.most_common(5)],
            top_missing_params=[{"param": key, "count": count} for key, count in missing_params.most_common(5)],
        ),
        unimplemented_tools,
        disallowed_actions,
        missing_params,
    )


def _safe_correlation(event_corr: str, payload_json: str) -> str | None:
    corr = str(event_corr or "").strip()
    if corr and corr.lower() != "n/a":
        return corr
    payload = _parse_payload(payload_json)
    payload_corr = str(payload.get("correlation_id") or "").strip()
    return payload_corr or None


def _rate(numerator: int, denominator: int) -> float:
    return round(numerator / denominator, 4) if denominator > 0 else 0.0


async def retro_summary(session: AsyncSession, period_days: int) -> RetroSummary:
    rows = await _load_event_rows(session, period_days, _SUMMARY_EVENT_TYPES)
    return _build_summary(rows, period_days)


async def retro_summary_with_deltas(session: AsyncSession, period_days: int) -> RetroSummaryWithDeltas:
    _validate_period_days(period_days)
    now = utcnow()
    current_rows = await _query_window(
        session,
        start_at=now - timedelta(days=period_days),
        end_at=now,
        event_types=_SUMMARY_EVENT_TYPES,
    )
    previous_rows = await _query_window(
        session,
        start_at=now - timedelta(days=period_days * 2),
        end_at=now - timedelta(days=period_days),
        event_types=_SUMMARY_EVENT_TYPES,
    )
    current = _build_summary(current_rows, period_days)
    previous = _build_summary(previous_rows, period_days)

    deltas = {
        "advice_total_delta": _delta_value(current.totals["advice_total"], previous.totals["advice_total"]),
        "tool_calls_total_delta": _delta_value(current.totals["tool_calls_total"], previous.totals["tool_calls_total"]),
        "plans_committed_delta": _delta_value(current.totals["plans_committed_total"], previous.totals["plans_committed_total"]),
        "memo_generated_delta": _delta_value(current.totals["memos_generated_total"], previous.totals["memos_generated_total"]),
        "unknown_total_delta": _delta_value(int(current.failures["unknown_total"]), int(previous.failures["unknown_total"])),
        "quality_confidence_delta": {
            "TOOL": {
                level: _delta_value(
                    int(current.quality["confidence_counts"]["TOOL"][level]),
                    int(previous.quality["confidence_counts"]["TOOL"][level]),
                )
                for level in ("high", "med", "low")
            },
            "ADVICE": {
                level: _delta_value(
                    int(current.quality["confidence_counts"]["ADVICE"][level]),
                    int(previous.quality["confidence_counts"]["ADVICE"][level]),
                )
                for level in ("high", "med", "low")
            },
        },
    }

    current_tools = Counter({str(item["tool_name"]): int(item["count"]) for item in current.top_tools if item.get("tool_name")})
    previous_tools = Counter({str(item["tool_name"]): int(item["count"]) for item in previous.top_tools if item.get("tool_name")})
    deltas["top_tools_delta"] = _counter_delta(current_tools, previous_tools, "tool_name")

    return RetroSummaryWithDeltas(current=current, previous=previous, deltas=deltas)


async def retro_gaps(session: AsyncSession, period_days: int) -> RetroGaps:
    rows = await _load_event_rows(session, period_days, _GAPS_EVENT_TYPES)
    gaps, _, _, _ = _build_gaps(rows, period_days)
    return gaps


async def retro_gaps_with_deltas(session: AsyncSession, period_days: int) -> RetroGapsWithDeltas:
    _validate_period_days(period_days)
    now = utcnow()
    current_rows = await _query_window(
        session,
        start_at=now - timedelta(days=period_days),
        end_at=now,
        event_types=_GAPS_EVENT_TYPES,
    )
    previous_rows = await _query_window(
        session,
        start_at=now - timedelta(days=period_days * 2),
        end_at=now - timedelta(days=period_days),
        event_types=_GAPS_EVENT_TYPES,
    )

    current, current_unimpl, _, current_missing = _build_gaps(current_rows, period_days)
    previous, previous_unimpl, _, previous_missing = _build_gaps(previous_rows, period_days)

    deltas = {
        "top_unimplemented_tools_delta": _counter_delta(current_unimpl, previous_unimpl, "tool_name"),
        "top_missing_params_delta": _counter_delta(current_missing, previous_missing, "param"),
    }

    return RetroGapsWithDeltas(current=current, previous=previous, deltas=deltas)


async def retro_funnels(session: AsyncSession, period_days: int) -> FunnelReport:
    rows = await _load_event_rows(session, period_days, _FUNNEL_EVENT_TYPES)

    plan_map = {
        "agent_plan_built": "built",
        "agent_plan_previewed": "previewed",
        "agent_plan_previewed_v2": "previewed",
        "agent_plan_committed": "committed",
        "agent_plan_committed_v2": "committed",
        "agent_plan_cancelled": "cancelled",
    }
    advice_map = {
        "advice_data_brief_requested": "brief",
        "advice_data_brief_built": "brief",
        "advice_data_brief_cache_hit": "brief",
        "advice_playbook_used": "advice",
        "advice_generated": "advice",
        "advice_actions_suggested": "advice",
        "advice_memo_generated": "memo",
    }

    by_corr_plan: dict[str, set[str]] = {}
    by_corr_advice: dict[str, set[str]] = {}
    missing_corr = 0
    plan_fallback_counter: Counter[str] = Counter()
    advice_fallback_counter: Counter[str] = Counter()

    for event_type, payload_json, event_corr in rows:
        stage = plan_map.get(event_type)
        if stage:
            plan_fallback_counter[stage] += 1
            corr = _safe_correlation(event_corr, payload_json)
            if corr:
                by_corr_plan.setdefault(corr, set()).add(stage)
            else:
                missing_corr += 1

        advice_stage = advice_map.get(event_type)
        if advice_stage:
            advice_fallback_counter[advice_stage] += 1
            corr = _safe_correlation(event_corr, payload_json)
            if corr:
                by_corr_advice.setdefault(corr, set()).add(advice_stage)
            else:
                missing_corr += 1

    notes: list[str] = []

    if by_corr_plan:
        built = sum(1 for stages in by_corr_plan.values() if "built" in stages)
        previewed = sum(1 for stages in by_corr_plan.values() if "previewed" in stages)
        committed = sum(1 for stages in by_corr_plan.values() if "committed" in stages)
        cancelled = sum(1 for stages in by_corr_plan.values() if "cancelled" in stages)
    else:
        built = plan_fallback_counter["built"]
        previewed = plan_fallback_counter["previewed"]
        committed = plan_fallback_counter["committed"]
        cancelled = plan_fallback_counter["cancelled"]
        notes.append("Plan funnel fallback: correlation_id unavailable, used event ordering counts.")

    if by_corr_advice:
        brief = sum(1 for stages in by_corr_advice.values() if "brief" in stages)
        advice = sum(1 for stages in by_corr_advice.values() if "advice" in stages)
        memo = sum(1 for stages in by_corr_advice.values() if "memo" in stages)
    else:
        brief = advice_fallback_counter["brief"]
        advice = advice_fallback_counter["advice"]
        memo = advice_fallback_counter["memo"]
        notes.append("Advice funnel fallback: correlation_id unavailable, used event ordering counts.")

    total_events = max(1, len(rows) * 2)
    corr_coverage = 1 - (missing_corr / total_events)
    if corr_coverage > 0.9:
        confidence = "high"
    elif corr_coverage > 0.4:
        confidence = "med"
    else:
        confidence = "low"

    plan = {
        "built": built,
        "previewed": previewed,
        "committed": committed,
        "cancelled": cancelled,
        "rates": {
            "preview_per_built": _rate(previewed, built),
            "commit_per_preview": _rate(committed, previewed),
            "cancel_per_built": _rate(cancelled, built),
        },
    }
    advice_block = {
        "brief": brief,
        "advice": advice,
        "memo": memo,
        "rates": {"memo_per_advice": _rate(memo, advice)},
    }

    return FunnelReport(period_days=period_days, plan=plan, advice=advice_block, confidence=confidence, notes=notes)
