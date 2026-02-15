from app.notify.renderers import render_ops_pdf


def test_render_ops_pdf_handles_empty_snapshot() -> None:
    pdf = render_ops_pdf({}, report_title="Ops Report", tz="Europe/Berlin")

    assert isinstance(pdf, bytes)
    assert len(pdf) > 0
