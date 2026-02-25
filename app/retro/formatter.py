from __future__ import annotations

import re

from app.retro.service import RetroGaps, RetroSummary

_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")


def safe_str(value: object) -> str:
    text = str(value or "").replace("\n", " ").replace("\r", " ").strip()
    text = _EMAIL_RE.sub("[redacted_email]", text)
    text = _PHONE_RE.sub("[redacted_phone]", text)
    return text[:120]


def _fmt_top(items: list[dict[str, object]], key: str) -> str:
    if not items:
        return "нет данных"
    return ", ".join(f"{safe_str(item.get(key))}({item.get('count', 0)})" for item in items)


def _fmt_delta(metric: dict[str, object]) -> str:
    absolute = metric.get("absolute", 0)
    percent = metric.get("percent")
    if percent is None:
        return f"{absolute:+d}" if isinstance(absolute, int) else str(absolute)
    return f"{absolute:+d} ({percent:+.1f}%)" if isinstance(absolute, int) else f"{absolute} ({percent}%)"


def format_retro_summary(summary: RetroSummary, deltas: dict[str, object] | None = None) -> str:
    totals = summary.totals
    routing = summary.routing
    tool_conf = summary.quality["confidence_counts"]["TOOL"]
    advice_conf = summary.quality["confidence_counts"]["ADVICE"]

    lines = [
        f"📊 Retro ({summary.period_days}d)",
        "",
        "📊 Usage",
        (
            "advice={advice}, tool={tool}, plans={preview} (commit={commit}), memo={memo}, briefs={briefs}".format(
                advice=totals["advice_total"],
                tool=totals["tool_calls_total"],
                preview=totals["plans_previewed_total"],
                commit=totals["plans_committed_total"],
                memo=totals["memos_generated_total"],
                briefs=totals["briefs_built_total"],
            )
        ),
        "",
        "🧭 Routing",
        (
            f"rule={routing['rule_hits_total']}, llm={routing['llm_plans_total']}, "
            f"llm_rate={round(float(routing['llm_fallback_rate']) * 100, 1)}%"
        ),
        "",
        "🧪 Quality",
        f"TOOL high/med/low = {tool_conf['high']}/{tool_conf['med']}/{tool_conf['low']}",
        f"ADVICE high/med/low = {advice_conf['high']}/{advice_conf['med']}/{advice_conf['low']}",
        f"warnings: {_fmt_top(summary.quality['top_warning_codes'], 'warning')}",
        "",
        "⚠️ Failures",
        f"unknown_total={summary.failures['unknown_total']}",
        f"unknown reasons: {_fmt_top(summary.failures['top_unknown_reasons'], 'reason')}",
        "",
        "🧰 Top tools",
        _fmt_top(summary.top_tools, "tool_name"),
    ]

    if deltas:
        lines.extend(
            [
                "",
                "📈 Trend vs previous window",
                f"advice: {_fmt_delta(deltas.get('advice_total_delta', {}))}",
                f"tool calls: {_fmt_delta(deltas.get('tool_calls_total_delta', {}))}",
                f"plans committed: {_fmt_delta(deltas.get('plans_committed_delta', {}))}",
                f"memo generated: {_fmt_delta(deltas.get('memo_generated_delta', {}))}",
                f"unknown total: {_fmt_delta(deltas.get('unknown_total_delta', {}))}",
            ]
        )
    return "\n".join(lines)


def format_retro_gaps(gaps: RetroGaps) -> str:
    def _bullet(title: str, items: list[dict[str, object]], key: str, hint: str) -> list[str]:
        if not items:
            return [f"• {title}: нет данных", f"  что делать: {hint}"]
        formatted = ", ".join(f"{safe_str(item.get(key))}({item.get('count', 0)})" for item in items)
        return [f"• {title}: {formatted}", f"  что делать: {hint}"]

    lines = [f"📦 Gap report ({gaps.period_days}d)", ""]
    lines.extend(_bullet("UPSTREAM_NOT_IMPLEMENTED", gaps.top_unimplemented_tools, "tool_name", "добавить реализацию/капабилити в SIS."))
    lines.append("")
    lines.extend(_bullet("ACTION_TOOL_NOT_ALLOWED", gaps.top_disallowed_actions, "tool_name", "проверить allowlist LLM action tools."))
    lines.append("")
    lines.extend(_bullet("Missing params (wizard)", gaps.top_missing_params, "param", "добавить подсказки и preset-значения в template/wizard."))
    return "\n".join(lines)
