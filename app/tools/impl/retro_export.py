from __future__ import annotations

import json
import re
from typing import Any

from pydantic import BaseModel, Field

from app.core.audit import write_audit_event
from app.core.time import utcnow
from app.retro.service import retro_funnels, retro_gaps_with_deltas, retro_summary_with_deltas
from app.tools.contracts import ToolArtifact, ToolProvenance, ToolResponse

_EMAIL_RE = re.compile(r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}", re.IGNORECASE)
_PHONE_RE = re.compile(r"\+?\d[\d\s().-]{7,}\d")


class Payload(BaseModel):
    period_days: int = Field(default=7)
    include_gaps: bool = Field(default=True)
    include_funnels: bool = Field(default=True)
    format: str = Field(default="json")


def _redact_str(value: str) -> str:
    redacted = _EMAIL_RE.sub("[redacted_email]", value)
    redacted = _PHONE_RE.sub("[redacted_phone]", redacted)
    return redacted.replace("\n", " ").replace("\r", " ")[:120]


def _sanitize(obj: Any) -> Any:
    if isinstance(obj, dict):
        return {str(k): _sanitize(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_sanitize(v) for v in obj]
    if isinstance(obj, str):
        return _redact_str(obj)
    return obj


async def handle(payload: Payload, correlation_id: str, session) -> ToolResponse:
    if payload.period_days not in {7, 30}:
        return ToolResponse.fail(correlation_id=correlation_id, code="VALIDATION_ERROR", message="period_days must be 7 or 30")
    if payload.format != "json":
        return ToolResponse.fail(correlation_id=correlation_id, code="VALIDATION_ERROR", message="format must be json")

    generated_at = utcnow().isoformat()
    summary_report = await retro_summary_with_deltas(session, payload.period_days)

    full_payload: dict[str, object] = {
        "period_days": payload.period_days,
        "generated_at": generated_at,
        "summary": summary_report.to_dict(),
    }
    if payload.include_gaps:
        full_payload["gaps"] = (await retro_gaps_with_deltas(session, payload.period_days)).to_dict()
    if payload.include_funnels:
        full_payload["funnels"] = (await retro_funnels(session, payload.period_days)).to_dict()

    safe_payload = _sanitize(full_payload)
    rendered = json.dumps(safe_payload, ensure_ascii=False, indent=2)

    await write_audit_event(
        "retro_viewed",
        {"period_days": payload.period_days, "kind": "export", "include_gaps": payload.include_gaps, "include_funnels": payload.include_funnels},
        correlation_id=correlation_id,
    )

    artifact = ToolArtifact(type="json", filename=f"retro_{payload.period_days}d.json", content=rendered.encode("utf-8"))
    return ToolResponse.ok(
        correlation_id=correlation_id,
        data={
            "period_days": payload.period_days,
            "generated_at": generated_at,
            "include_gaps": payload.include_gaps,
            "include_funnels": payload.include_funnels,
            "artifact": artifact.filename,
        },
        artifacts=[artifact],
        provenance=ToolProvenance(
            sources=["ownerbot_audit_events"],
            window={"scope": "retro", "type": "rolling", "days": payload.period_days},
            filters_hash=f"retro_export:{payload.period_days}:{int(payload.include_gaps)}:{int(payload.include_funnels)}",
        ),
    )
