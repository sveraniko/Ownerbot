from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Any, Awaitable, Callable, Literal

from app.advice.classifier import AdviceTopic
from app.core.redis import get_redis
from app.tools.contracts import ToolResponse


ToolRunner = Callable[[str, dict[str, Any]], Awaitable[ToolResponse]]


@dataclass(frozen=True)
class ToolCallSpec:
    tool: str
    payload: dict[str, Any] = field(default_factory=dict)


@dataclass
class DataBriefRequest:
    topic: AdviceTopic
    mode: Literal["auto", "manual"] = "auto"
    tool_set: list[ToolCallSpec] = field(default_factory=list)
    window: dict[str, Any] = field(default_factory=dict)


@dataclass
class DataBriefResult:
    created_at: str
    topic: AdviceTopic
    tools_run: list[dict[str, Any]]
    facts: dict[str, Any]
    summary: str
    warnings: list[str]

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "topic": self.topic.value,
            "tools_run": self.tools_run,
            "facts": self.facts,
            "summary": self.summary,
            "warnings": self.warnings,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DataBriefResult":
        topic_raw = str(data.get("topic") or AdviceTopic.NONE.value)
        try:
            topic = AdviceTopic(topic_raw)
        except ValueError:
            topic = AdviceTopic.NONE
        return cls(
            created_at=str(data.get("created_at") or _utc_now_iso()),
            topic=topic,
            tools_run=list(data.get("tools_run") or []),
            facts=dict(data.get("facts") or {}),
            summary=str(data.get("summary") or ""),
            warnings=[str(item) for item in (data.get("warnings") or [])],
        )


_BRIEF_TTL_SECONDS = 15 * 60
_COOLDOWN_SECONDS = 120


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _cache_key(chat_id: int, topic: AdviceTopic) -> str:
    return f"ownerbot:advice:brief:{chat_id}:{topic.value}"


def _cooldown_key(chat_id: int, topic: AdviceTopic) -> str:
    return f"ownerbot:advice:brief:cooldown:{chat_id}:{topic.value}"


def select_tool_set(topic: AdviceTopic) -> list[ToolCallSpec]:
    mapping: dict[AdviceTopic, list[ToolCallSpec]] = {
        AdviceTopic.SEASON_TRENDS: [
            ToolCallSpec(tool="top_products", payload={"days": 30, "group_by": "category", "limit": 5}),
            ToolCallSpec(tool="revenue_trend", payload={"days": 30}),
            ToolCallSpec(tool="inventory_status", payload={"section": "all", "limit": 5}),
        ],
        AdviceTopic.ASSORTMENT_STRATEGY: [
            ToolCallSpec(tool="top_products", payload={"days": 30, "group_by": "category", "limit": 5}),
            ToolCallSpec(tool="revenue_trend", payload={"days": 30}),
            ToolCallSpec(tool="inventory_status", payload={"section": "all", "limit": 5}),
        ],
        AdviceTopic.PROMO_STRATEGY: [
            ToolCallSpec(tool="kpi_compare", payload={"preset": "wow"}),
            ToolCallSpec(tool="revenue_trend", payload={"days": 14}),
            ToolCallSpec(tool="top_products", payload={"days": 7, "limit": 5}),
        ],
        AdviceTopic.PRICING_STRATEGY: [
            ToolCallSpec(tool="sis_fx_status", payload={}),
            ToolCallSpec(tool="kpi_compare", payload={"preset": "wow"}),
            ToolCallSpec(tool="revenue_trend", payload={"days": 30}),
        ],
        AdviceTopic.OPS_PRIORITY: [
            ToolCallSpec(tool="team_queue_summary", payload={}),
            ToolCallSpec(tool="orders_search", payload={"preset": "stuck", "limit": 20}),
            ToolCallSpec(tool="orders_search", payload={"preset": "payment_issues", "limit": 20}),
            ToolCallSpec(tool="sys_last_errors", payload={"limit": 20}),
        ],
        AdviceTopic.GROWTH_PLAN: [
            ToolCallSpec(tool="kpi_compare", payload={"preset": "mom"}),
            ToolCallSpec(tool="revenue_trend", payload={"days": 30}),
            ToolCallSpec(tool="top_products", payload={"days": 30, "limit": 5}),
        ],
    }
    return list(mapping.get(topic, []))


def _as_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _normalize_response_facts(tool: str, data: dict[str, Any], facts: dict[str, Any]) -> None:
    if tool == "kpi_compare":
        kpi = dict(facts.get("kpi") or {})
        totals_a = dict(data.get("totals_a") or {})
        totals_b = dict(data.get("totals_b") or {})
        delta = dict(data.get("delta") or {})
        kpi.update(
            {
                "revenue_net_a": _as_float(totals_a.get("revenue_net_sum")),
                "revenue_net_b": _as_float(totals_b.get("revenue_net_sum")),
                "orders_paid_a": totals_a.get("orders_paid_sum"),
                "orders_paid_b": totals_b.get("orders_paid_sum"),
                "aov_a": _as_float(data.get("aov_a")),
                "aov_b": _as_float(data.get("aov_b")),
                "wow_delta_pct": ((delta.get("revenue_net_sum") or {}).get("delta_pct")),
            }
        )
        facts["kpi"] = kpi

    if tool == "revenue_trend":
        totals = dict(data.get("totals") or {})
        delta = dict(data.get("delta_vs_prev_window") or {})
        trend = {
            "days": data.get("days"),
            "revenue_net": _as_float(totals.get("revenue_net")),
            "orders_paid": totals.get("orders_paid"),
            "slope_hint": "up" if (_as_float(delta.get("revenue_net_pct")) or 0.0) > 0 else "down_or_flat",
            "delta_revenue_pct": _as_float(delta.get("revenue_net_pct")),
        }
        facts["trend"] = trend

    if tool == "top_products":
        rows = list(data.get("rows") or [])
        tops = []
        for item in rows[:5]:
            tops.append(
                {
                    "title": item.get("title") or item.get("key"),
                    "category": item.get("category"),
                    "revenue": _as_float(item.get("revenue")),
                    "qty": item.get("qty"),
                }
            )
        facts["tops"] = tops

    if tool == "inventory_status":
        counts = dict(data.get("counts") or {})
        facts["inventory"] = {
            "out_of_stock": counts.get("out_of_stock", 0),
            "low_stock": counts.get("low_stock", 0),
            "missing_photo": counts.get("missing_photo", 0),
            "missing_price": counts.get("missing_price", 0),
        }

    if tool == "team_queue_summary":
        ops = dict(facts.get("ops") or {})
        ops.update(
            {
                "unanswered": data.get("total_open_threads", 0),
                "unanswered_2h": data.get("unanswered_2h", 0),
                "errors": ops.get("errors", 0),
            }
        )
        facts["ops"] = ops

    if tool == "chats_unanswered":
        ops = dict(facts.get("ops") or {})
        ops["unanswered"] = data.get("count", 0)
        facts["ops"] = ops

    if tool == "orders_search":
        ops = dict(facts.get("ops") or {})
        preset = str((data.get("applied_filters") or {}).get("preset") or "")
        count = int(data.get("count") or 0)
        if preset == "stuck":
            ops["stuck"] = count
        if preset == "payment_issues":
            ops["payment_issues"] = count
        facts["ops"] = ops

    if tool == "sys_last_errors":
        ops = dict(facts.get("ops") or {})
        ops["errors"] = int(data.get("count") or 0)
        facts["ops"] = ops

    if tool == "sis_fx_status":
        facts["fx"] = {
            "base_currency": data.get("base_currency"),
            "shop_currency": data.get("shop_currency"),
            "latest_rate": _as_float(data.get("latest_rate")),
            "would_apply": data.get("would_apply"),
        }


def _build_summary(topic: AdviceTopic, facts: dict[str, Any], warnings: list[str]) -> str:
    lines: list[str] = [f"Тема: {topic.value}"]
    kpi = facts.get("kpi") if isinstance(facts.get("kpi"), dict) else {}
    if kpi:
        lines.append(
            "KPI: net A={a} vs B={b}, AOV {aov}".format(
                a=round(float(kpi.get("revenue_net_a") or 0), 2),
                b=round(float(kpi.get("revenue_net_b") or 0), 2),
                aov=round(float(kpi.get("aov_a") or 0), 2),
            )
        )
    trend = facts.get("trend") if isinstance(facts.get("trend"), dict) else {}
    if trend:
        lines.append(
            f"Тренд {trend.get('days')}d: net={round(float(trend.get('revenue_net') or 0), 2)}, slope={trend.get('slope_hint')}"
        )
    tops = facts.get("tops") if isinstance(facts.get("tops"), list) else []
    if tops:
        names = ", ".join(str(item.get("title") or "—") for item in tops[:3])
        lines.append(f"Топ: {names}")
    inventory = facts.get("inventory") if isinstance(facts.get("inventory"), dict) else {}
    if inventory:
        lines.append(
            "Остатки: OOS={oos}, low={low}, no_photo={photo}, no_price={price}".format(
                oos=inventory.get("out_of_stock", 0),
                low=inventory.get("low_stock", 0),
                photo=inventory.get("missing_photo", 0),
                price=inventory.get("missing_price", 0),
            )
        )
    ops = facts.get("ops") if isinstance(facts.get("ops"), dict) else {}
    if ops:
        lines.append(
            "Ops: unanswered={u}, stuck={s}, pay_issues={p}, errors={e}".format(
                u=ops.get("unanswered", 0),
                s=ops.get("stuck", 0),
                p=ops.get("payment_issues", 0),
                e=ops.get("errors", 0),
            )
        )
    fx = facts.get("fx") if isinstance(facts.get("fx"), dict) else {}
    if fx:
        lines.append(
            "FX: {base}/{shop}={rate} ({apply})".format(
                base=fx.get("base_currency") or "?",
                shop=fx.get("shop_currency") or "?",
                rate=fx.get("latest_rate") or "?",
                apply="apply" if fx.get("would_apply") else "hold",
            )
        )
    if warnings:
        lines.append(f"⚠️ предупреждений: {len(warnings)}")
    return "\n".join(lines[:10])


async def run_tool_set_sequential(
    *,
    topic: AdviceTopic,
    tool_runner: ToolRunner,
    calls: list[ToolCallSpec],
) -> DataBriefResult:
    warnings: list[str] = []
    tools_run: list[dict[str, Any]] = []
    facts: dict[str, Any] = {"windows": {}}

    for call in calls[:4]:
        response = await tool_runner(call.tool, dict(call.payload))
        tools_run.append(
            {
                "tool": call.tool,
                "ok": response.status == "ok",
                "warnings_count": len(response.warnings),
            }
        )
        if response.provenance.window is not None:
            facts["windows"][call.tool] = response.provenance.window
        if response.status == "ok":
            _normalize_response_facts(call.tool, dict(response.data), facts)
        else:
            code = response.error.code if response.error else "UNKNOWN"
            warnings.append(f"{call.tool}: {code}")
        for warning in response.warnings[:3]:
            warnings.append(f"{call.tool}: {warning.message}")

    summary = _build_summary(topic, facts, warnings)
    return DataBriefResult(
        created_at=_utc_now_iso(),
        topic=topic,
        tools_run=tools_run,
        facts=facts,
        summary=summary,
        warnings=warnings[:8],
    )


async def load_cached_brief(chat_id: int, topic: AdviceTopic) -> DataBriefResult | None:
    redis = await get_redis()
    raw = await redis.get(_cache_key(chat_id, topic))
    if not raw:
        return None
    payload = json.loads(raw.decode("utf-8") if isinstance(raw, bytes) else raw)
    return DataBriefResult.from_dict(dict(payload))


async def save_brief_cache(chat_id: int, brief: DataBriefResult) -> None:
    redis = await get_redis()
    await redis.set(_cache_key(chat_id, brief.topic), json.dumps(brief.to_dict(), ensure_ascii=False), ex=_BRIEF_TTL_SECONDS)


async def is_cooldown_active(chat_id: int, topic: AdviceTopic) -> bool:
    redis = await get_redis()
    return bool(await redis.get(_cooldown_key(chat_id, topic)))


async def set_brief_cooldown(chat_id: int, topic: AdviceTopic) -> None:
    redis = await get_redis()
    await redis.set(_cooldown_key(chat_id, topic), "1", ex=_COOLDOWN_SECONDS)
