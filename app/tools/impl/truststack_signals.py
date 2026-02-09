from __future__ import annotations

from app.tools.impl.stub_utils import StubPayload, not_implemented
from app.tools.contracts import ToolResponse


Payload = StubPayload


async def handle(payload: Payload, correlation_id: str, session) -> ToolResponse:
    return not_implemented(correlation_id, "truststack_signals")
