from __future__ import annotations

from pathlib import Path


def test_baseline_contains_critical_perf_indexes() -> None:
    source = Path("app/storage/alembic/versions/0001_baseline.py").read_text(encoding="utf-8")

    for index_name in (
        "idx_ownerbot_audit_events_event_type_occurred_at",
        "idx_ownerbot_action_log_status_committed_at",
        "idx_ownerbot_action_log_tool_committed_at",
        "idx_ownerbot_demo_orders_status_created_at",
    ):
        assert index_name in source
