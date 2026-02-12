import pytest


def test_render_revenue_trend_png_signature() -> None:
    pytest.importorskip("matplotlib")
    from app.reports.charts import render_revenue_trend_png

    series = [
        {"day": "2026-01-01", "revenue_gross": 120.0, "orders_paid": 2},
        {"day": "2026-01-02", "revenue_gross": 180.5, "orders_paid": 3},
    ]
    content = render_revenue_trend_png(
        series=series,
        currency="EUR",
        title="Revenue trend — последние 2 дней",
        tz="Europe/Berlin",
    )

    assert isinstance(content, bytes)
    assert content.startswith(b"\x89PNG\r\n\x1a\n")


def test_build_weekly_report_pdf_signature() -> None:
    pytest.importorskip("reportlab")
    from app.reports.pdf_weekly import build_weekly_report_pdf

    content = build_weekly_report_pdf(
        {
            "generated_at": "2026-01-07T10:00:00Z",
            "correlation_id": "corr-1",
            "kpi_summary": ["day=2026-01-07", "revenue_gross=199.0"],
            "revenue_summary": ["total=700.0 EUR", "avg/day=100.0 EUR"],
            "stuck_orders": ["OB-1 | stuck | 99 EUR"],
            "unanswered_chats": ["thr-1 | customer=c-1"],
        }
    )

    assert isinstance(content, bytes)
    assert content.startswith(b"%PDF")
