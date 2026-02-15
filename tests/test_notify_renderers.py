from app.notify.digest_builder import DigestBundle
from app.notify.renderers import render_revenue_trend_png, render_weekly_pdf


def test_png_renderer_returns_bytes() -> None:
    content = render_revenue_trend_png([], "title", "subtitle")
    assert isinstance(content, bytes)
    assert len(content) > 100


def test_pdf_renderer_returns_bytes() -> None:
    bundle = DigestBundle(
        text="Weekly",
        kpi_summary={"revenue_net_sum": 100, "orders_paid_sum": 5, "aov": 20},
        series=[{"day": "2026-01-01", "revenue_net": 100}],
        ops_summary={"unanswered_chats_2h": 1, "stuck_orders": 2, "last_errors_count": 0},
        fx_summary={},
        warnings=[],
    )
    content = render_weekly_pdf(bundle)
    assert isinstance(content, bytes)
    assert len(content) > 200
