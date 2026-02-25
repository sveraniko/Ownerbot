from __future__ import annotations

from datetime import datetime, timezone
from io import BytesIO
from zoneinfo import ZoneInfo

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.pdfgen import canvas

from app.advice.data_brief import DataBriefResult


_MAX_BULLET_LEN = 160


def _trim(text: str, limit: int = _MAX_BULLET_LEN) -> str:
    value = " ".join(str(text or "").split())
    if len(value) <= limit:
        return value
    return value[: limit - 1] + "…"


def _line(pdf: canvas.Canvas, text: str, y: float, *, bold: bool = False, size: int = 10) -> float:
    if y < 18 * mm:
        pdf.showPage()
        y = A4[1] - 20 * mm
    pdf.setFont("Helvetica-Bold" if bold else "Helvetica", size)
    pdf.drawString(18 * mm, y, text)
    return y - 6 * mm


def _section(pdf: canvas.Canvas, y: float, title: str, items: list[str], max_items: int) -> float:
    y = _line(pdf, title, y, bold=True)
    if not items:
        return _line(pdf, "- n/a", y)
    for item in items[:max_items]:
        y = _line(pdf, f"- {_trim(item)}", y)
    return y


def _brief_facts_lines(brief: DataBriefResult | None) -> list[str]:
    if brief is None:
        return ["No brief cached. Memo generated from advice context only."]
    lines: list[str] = []
    summary = _trim(brief.summary)
    if summary:
        lines.extend([part for part in summary.split("\n") if part.strip()])
    facts = brief.facts if isinstance(brief.facts, dict) else {}
    kpi = facts.get("kpi") if isinstance(facts.get("kpi"), dict) else {}
    if kpi:
        lines.append(
            "KPI: revenue a/b={a}/{b}, orders a/b={oa}/{ob}, aov a/b={aov_a}/{aov_b}, wow={wow}".format(
                a=kpi.get("revenue_net_a", "n/a"),
                b=kpi.get("revenue_net_b", "n/a"),
                oa=kpi.get("orders_paid_a", "n/a"),
                ob=kpi.get("orders_paid_b", "n/a"),
                aov_a=kpi.get("aov_a", "n/a"),
                aov_b=kpi.get("aov_b", "n/a"),
                wow=kpi.get("wow_delta_pct", "n/a"),
            )
        )
    trend = facts.get("trend") if isinstance(facts.get("trend"), dict) else {}
    if trend:
        lines.append(
            "Trend: days={days}, revenue={rev}, orders={orders}, delta={delta}, slope={slope}".format(
                days=trend.get("days", "n/a"),
                rev=trend.get("revenue_net", "n/a"),
                orders=trend.get("orders_paid", "n/a"),
                delta=trend.get("delta_revenue_pct", "n/a"),
                slope=trend.get("slope_hint", "n/a"),
            )
        )
    tops = facts.get("tops") if isinstance(facts.get("tops"), list) else []
    if tops:
        top_names = [str(item.get("name") or item.get("title") or item.get("sku") or "n/a") for item in tops[:3] if isinstance(item, dict)]
        if top_names:
            lines.append(f"Top items: {', '.join(top_names)}")
    inventory = facts.get("inventory") if isinstance(facts.get("inventory"), dict) else {}
    if inventory:
        lines.append(
            "Inventory: out={out}, low={low}, no_photo={photo}, no_price={price}".format(
                out=inventory.get("out_of_stock", 0),
                low=inventory.get("low_stock", 0),
                photo=inventory.get("missing_photo", 0),
                price=inventory.get("missing_price", 0),
            )
        )
    ops = facts.get("ops") if isinstance(facts.get("ops"), dict) else {}
    if ops:
        lines.append(
            "Ops: unanswered={u}, stuck={s}, payment_issues={p}, errors={e}".format(
                u=ops.get("unanswered", 0),
                s=ops.get("stuck", 0),
                p=ops.get("payment_issues", 0),
                e=ops.get("errors", 0),
            )
        )
    fx = facts.get("fx") if isinstance(facts.get("fx"), dict) else {}
    if fx:
        lines.append(
            "FX: {base}/{shop}={rate}, would_apply={apply}".format(
                base=fx.get("base_currency") or "?",
                shop=fx.get("shop_currency") or "?",
                rate=fx.get("latest_rate") or "?",
                apply=bool(fx.get("would_apply")),
            )
        )
    return [_trim(item) for item in lines if str(item).strip()]


def _now_in_tz(tz: str) -> str:
    now = datetime.now(timezone.utc)
    try:
        now = now.astimezone(ZoneInfo(tz))
    except Exception:
        return now.isoformat()
    return now.isoformat()


def render_decision_memo_pdf(topic: str, brief: DataBriefResult | None, advice_cache: dict, tz: str = "Europe/Berlin") -> bytes:
    hypotheses = [str(item) for item in (advice_cache.get("hypotheses") or []) if str(item).strip()]
    risks = [str(item) for item in (advice_cache.get("risks") or []) if str(item).strip()]
    experiments = [str(item) for item in (advice_cache.get("experiments") or []) if str(item).strip()]
    suggested_actions = [item for item in (advice_cache.get("suggested_actions") or []) if isinstance(item, dict)]

    proposed_actions: list[str] = []
    for action in suggested_actions[:3]:
        label = str(action.get("label") or action.get("tool") or "Action")
        why = str(action.get("why") or "")
        proposed_actions.append(f"{label}: {why}" if why else label)

    buf = BytesIO()
    pdf = canvas.Canvas(buf, pagesize=A4, pageCompression=0)
    y = A4[1] - 18 * mm

    y = _line(pdf, "OwnerBot Decision Memo", y, bold=True, size=14)
    y = _line(pdf, f"Topic: {_trim(topic, 120)}", y)
    y = _line(pdf, f"Generated at: {_now_in_tz(tz)}", y)
    y -= 1 * mm

    y = _section(pdf, y, "📌 Data Brief (facts)", _brief_facts_lines(brief), max_items=10)
    y -= 1 * mm
    y = _section(pdf, y, "🧠 Recommendations (hypotheses)", hypotheses, max_items=7)
    y -= 1 * mm
    y = _section(pdf, y, "⚠️ Risks", risks, max_items=3)
    y -= 1 * mm
    y = _section(pdf, y, "🧪 Experiments / Validation", experiments, max_items=6)
    y -= 1 * mm
    y = _section(pdf, y, "✅ Proposed Actions (preview-only)", proposed_actions, max_items=3)
    y -= 1 * mm
    _line(pdf, "Actions require preview+confirm in OwnerBot", y, size=9)

    pdf.save()
    return buf.getvalue()
