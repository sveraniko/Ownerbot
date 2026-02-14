from app.reports.charts import render_revenue_trend_png
from app.reports.pdf_weekly import build_weekly_report_pdf


def test_png_builder_returns_bytes() -> None:
    content = render_revenue_trend_png(
        series=[{"day": "2026-01-01", "revenue_gross": 10.0}, {"day": "2026-01-02", "revenue_gross": 20.0}],
        currency="EUR",
        title="Trend",
        tz="Europe/Berlin",
    )
    assert isinstance(content, bytes)
    assert len(content) > 100


def test_weekly_pdf_builder_returns_non_empty_bytes() -> None:
    content = build_weekly_report_pdf(
        {
            "correlation_id": "corr",
            "currency": "EUR",
            "kpi": {"revenue_gross": 100.0, "orders_paid": 3, "aov": 33.3},
            "trend": {
                "series": [{"day": "2026-01-01", "revenue_gross": 40.0}, {"day": "2026-01-02", "revenue_gross": 60.0}],
                "totals": {"revenue_gross": 100.0},
                "delta_vs_prev_window": {"revenue_gross_pct": 5.5},
            },
            "stuck_orders": {"orders": []},
            "unanswered_chats": {"threads": []},
        }
    )
    assert isinstance(content, bytes)
    assert len(content) > 100
