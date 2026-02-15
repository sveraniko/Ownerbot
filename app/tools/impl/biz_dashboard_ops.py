from __future__ import annotations

import uuid
from typing import Any

from pydantic import BaseModel, Field

from app.core.redis import get_redis
from app.notify import build_ops_snapshot
from app.notify.renderers import render_ops_pdf
from app.tools.contracts import ToolActor, ToolArtifact, ToolProvenance, ToolResponse

_LOCK_TTL_SECONDS = 300
_COOLDOWN_TTL_SECONDS = 120


class Payload(BaseModel):
    format: str = Field(default="pdf", pattern="^(pdf)$")
    tz: str = "Europe/Berlin"
    rules: dict[str, Any] | None = None


async def handle(payload: Payload, correlation_id: str, session, actor: ToolActor | None = None) -> ToolResponse:
    if actor is None:
        return ToolResponse.fail(correlation_id=correlation_id, code="ACTOR_REQUIRED", message="Owner context is required.")

    owner_id = actor.owner_user_id
    redis = await get_redis()
    cooldown_key = f"ownerbot:biz:ops:cooldown:{owner_id}"
    lock_key = f"ownerbot:biz:ops:lock:{owner_id}"

    cooldown_active = await redis.get(cooldown_key)
    if cooldown_active:
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={"owner_id": owner_id, "message": "Cooldown active. Try again a bit later."},
            provenance=ToolProvenance(sources=["biz_dashboard_ops"], window={}),
        )

    lock_token = str(uuid.uuid4())
    lock_acquired = await redis.set(lock_key, lock_token, ex=_LOCK_TTL_SECONDS, nx=True)
    if not lock_acquired:
        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={"owner_id": owner_id, "message": "Already generating, try later."},
            provenance=ToolProvenance(sources=["biz_dashboard_ops"], window={}),
        )

    try:
        await redis.set(cooldown_key, "1", ex=_COOLDOWN_TTL_SECONDS)
        snapshot = await build_ops_snapshot(session, correlation_id, payload.rules or {})
        pdf = render_ops_pdf(snapshot, report_title="Ops Report", tz=payload.tz)

        unanswered = snapshot.get("unanswered_chats") or {}
        stuck = snapshot.get("stuck_orders") or {}
        payments = snapshot.get("payment_issues") or {}
        errors = snapshot.get("errors") or {}
        inventory = snapshot.get("inventory") or {}
        summary = (
            f"📦 Ops Report (tz={payload.tz})\n"
            f"💬 Unanswered >{int(unanswered.get('threshold_hours') or 0)}h: {int(unanswered.get('count') or 0)}\n"
            f"🧾 Stuck orders: {int(stuck.get('count') or 0)}\n"
            f"💳 Payment issues: {int(payments.get('count') or 0)}\n"
            f"⚠️ Errors({int(errors.get('window_hours') or 0)}h): {int(errors.get('count') or 0)}\n"
            f"📉 Stock: out={int(inventory.get('out_of_stock') or 0)}, low<={int(inventory.get('low_stock_lte') or 0)}: {int(inventory.get('low_stock') or 0)}"
        )

        counts = {
            "unanswered_chats": int(unanswered.get("count") or 0),
            "stuck_orders": int(stuck.get("count") or 0),
            "payment_issues": int(payments.get("count") or 0),
            "errors": int(errors.get("count") or 0),
            "inventory_out_of_stock": int(inventory.get("out_of_stock") or 0),
            "inventory_low_stock": int(inventory.get("low_stock") or 0),
        }

        return ToolResponse.ok(
            correlation_id=correlation_id,
            data={
                "owner_id": owner_id,
                "message": summary,
                "snapshot_counts": counts,
                "warnings": snapshot.get("warnings") or [],
            },
            artifacts=[
                ToolArtifact(
                    type="pdf",
                    filename="ops_report.pdf",
                    content=pdf,
                    caption="Ops Report",
                )
            ],
            provenance=ToolProvenance(sources=["build_ops_snapshot", "render_ops_pdf"], window={}),
        )
    finally:
        try:
            current = await redis.get(lock_key)
            if current == lock_token:
                await redis.delete(lock_key)
        except Exception:
            pass
