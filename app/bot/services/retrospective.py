from __future__ import annotations

from app.core.audit import write_audit_event
from app.quality.confidence import compute_data_confidence, compute_decision_confidence
from app.tools.contracts import ToolResponse


async def write_retrospective_event(
    *,
    correlation_id: str,
    input_kind: str,
    text: str,
    intent_source: str,
    llm_confidence: float,
    tool_name: str,
    response: ToolResponse,
    artifacts: list[str] | None = None,
) -> None:
    data_conf = compute_data_confidence(response)
    decision_conf = compute_decision_confidence(
        llm_confidence=llm_confidence,
        data_confidence=data_conf.score,
        had_errors=response.status == "error",
    )
    reasons = list(data_conf.reasons) + list(decision_conf.reasons)
    payload = {
        "input_kind": input_kind,
        "text_len": len(text or ""),
        "intent_source": intent_source,
        "tool": tool_name,
        "status": response.status,
        "data_confidence": data_conf.score,
        "decision_confidence": decision_conf.score,
        "reasons": reasons,
        "artifacts": artifacts or [],
    }
    await write_audit_event("retrospective", payload, correlation_id=correlation_id)
