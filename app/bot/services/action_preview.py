from __future__ import annotations

from app.tools.contracts import ToolResponse


def is_noop_preview(resp: ToolResponse) -> bool:
    data = resp.data or {}
    status = str(data.get("status", "")).lower()
    return (data.get("would_apply") is False) or (status in {"skipped", "noop", "no_change"})
