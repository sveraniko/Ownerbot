from __future__ import annotations

from app.tools.impl.stub_utils import ActionStubPayload, not_implemented
from app.tools.contracts import ToolResponse


Payload = ActionStubPayload


async def handle(payload: Payload, correlation_id: str, session) -> ToolResponse:
    return not_implemented(correlation_id, "flag_order")
