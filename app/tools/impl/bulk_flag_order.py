from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field
from sqlalchemy import select

from app.core.settings import get_settings
from app.core.time import utcnow
from app.storage.models import OwnerbotDemoOrder
from app.tools.contracts import ToolActor, ToolProvenance, ToolResponse
from app.tools.impl.orders_search import (
    OrdersSearchPayload,
    apply_orders_filters,
    build_applied_filters,
)


class Payload(BaseModel):
    preset: Literal["stuck", "late_ship", "payment_issues"] = "stuck"
    status: str | None = None
    q: str | None = None
    limit: int = Field(default=20, ge=1, le=200)
    reason: str = Field(default="needs_attention", min_length=1, max_length=200)
    dry_run: bool = True


async def handle(
    payload: Payload,
    correlation_id: str,
    session,
    actor: ToolActor | None = None,
) -> ToolResponse:
    settings = get_settings()
    if settings.upstream_mode != "DEMO":
        return ToolResponse.fail(
            correlation_id=correlation_id,
            code="UPSTREAM_NOT_IMPLEMENTED",
            message="Orders tools are not wired to SIS Actions API yet (draft contract only).",
        )

    now = utcnow()
    search_payload = OrdersSearchPayload(
        preset=payload.preset,
        status=payload.status,
        q=payload.q,
        limit=payload.limit,
    )
    stmt = apply_orders_filters(select(OwnerbotDemoOrder), search_payload, now)
    stmt = stmt.where(OwnerbotDemoOrder.flagged.is_(False))
    stmt = stmt.order_by(OwnerbotDemoOrder.created_at.desc()).limit(payload.limit)
    result = await session.execute(stmt)
    targets = result.scalars().all()
    target_ids = [row.order_id for row in targets]

    matched_count = len(target_ids)
    sample_ids = target_ids[:10]
    would_apply = matched_count > 0

    provenance = ToolProvenance(
        sources=["local_ownerbot"],
        window={"scope": "demo_orders", "type": "bulk_action"},
        filters_hash="bulk_flag",
    )

    if payload.dry_run:
        status = "preview" if would_apply else "noop"
        data = {
            "status": status,
            "would_apply": would_apply,
            "targets_count": matched_count,
            "matched_count": matched_count,
            "sample_order_ids": sample_ids,
            "reason": payload.reason,
            "applied_filters": build_applied_filters(search_payload),
        }
        if would_apply:
            data["note"] = "Требует подтверждения"
        return ToolResponse.ok(correlation_id=correlation_id, data=data, provenance=provenance)

    if not would_apply:
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={
                "status": "noop",
                "would_apply": False,
                "updated_count": 0,
                "matched_count": 0,
                "sample_order_ids": [],
                "reason": payload.reason,
                "applied_filters": build_applied_filters(search_payload),
            },
            provenance=provenance,
        )

    flag_time = utcnow()
    actor_id = actor.owner_user_id if actor else None
    for order in targets:
        order.flagged = True
        order.flag_reason = payload.reason
        order.flagged_at = flag_time
        order.flagged_by = actor_id
    await session.commit()

    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={
            "status": "committed",
            "would_apply": True,
            "updated_count": len(targets),
            "matched_count": matched_count,
            "sample_order_ids": sample_ids,
            "reason": payload.reason,
            "applied_filters": build_applied_filters(search_payload),
        },
        provenance=provenance,
    )
