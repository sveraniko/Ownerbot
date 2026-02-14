from pathlib import Path

import pytest

from app.templates.catalog.loader import TemplateCatalogLoaderError, load_template_catalog


def test_loader_loads_defs() -> None:
    catalog = load_template_catalog()
    assert catalog.get("PRC_BUMP").tool_name == "sis_prices_bump"
    assert "prices" in catalog.list_categories()


def test_loader_rejects_duplicate_template_id(tmp_path: Path) -> None:
    first = tmp_path / "one.yml"
    second = tmp_path / "two.yml"

    first.write_text(
        """
template_id: DUP_X
category: prices
title: t1
button_text: b1
kind: ACTION
tool_name: sis_prices_bump
default_payload: {}
inputs: []
""".strip(),
        encoding="utf-8",
    )
    second.write_text(
        """
template_id: DUP_X
category: products
title: t2
button_text: b2
kind: ACTION
tool_name: sis_products_publish
default_payload: {}
inputs: []
""".strip(),
        encoding="utf-8",
    )

    with pytest.raises(TemplateCatalogLoaderError):
        load_template_catalog(defs_dir=tmp_path)


def test_catalog_listing_stable() -> None:
    catalog = load_template_catalog()
    assert catalog.list_categories()[0:5] == ["reports", "orders", "team", "systems", "advanced"]
    assert "prices" in catalog.list_categories()
    assert "discounts" in catalog.list_categories()

    prices = [spec.button_text for spec in catalog.list_templates("prices")]
    assert prices == [
        "Поднять цены на %",
        "FX пересчёт цен",
        "FX статус",
        "FX обновить (по настройкам)",
        "FX расписание/пороги",
        "Откат последнего FX",
    ]
