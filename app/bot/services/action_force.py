from __future__ import annotations

from app.tools.contracts import ToolResponse


_FORCE_PREFIX = "MASS_CHANGE_OVER"


def requires_force_confirm(response: ToolResponse) -> bool:
    anomaly = response.data.get("anomaly") if isinstance(response.data, dict) else None
    over_count = int((anomaly or {}).get("over_threshold_count", 0) or 0)
    if over_count > 0:
        return True

    for warning in response.warnings:
        code = (warning.code or "").strip().upper()
        if code == "FORCE_REQUIRED" or code.startswith(_FORCE_PREFIX):
            return True
        # backward compatibility with old SIS warning text format
        if "force required for apply" in warning.message.lower():
            return True
    return False
