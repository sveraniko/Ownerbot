from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime, timedelta
from typing import Iterable

from sqlalchemy import and_, func, or_, select

from app.core.time import utcnow
from app.storage.models import OwnerbotDemoOrder, OwnerbotDemoOrderItem, OwnerbotDemoProduct


@dataclass(frozen=True)
class ForecastProduct:
    product_id: str
    title: str
    category: str
    stock_qty: int


def _normalize_categories(include_categories: list[str] | None) -> set[str] | None:
    if not include_categories:
        return None
    normalized = {category.strip().lower() for category in include_categories if category and category.strip()}
    return normalized or None


async def list_products(session, include_categories: list[str] | None) -> list[ForecastProduct]:
    rows = (await session.execute(select(OwnerbotDemoProduct).order_by(OwnerbotDemoProduct.product_id.asc()))).scalars().all()
    categories = _normalize_categories(include_categories)
    if categories is None:
        selected = rows
    else:
        selected = [row for row in rows if (row.category or "").strip().lower() in categories]

    return [
        ForecastProduct(product_id=row.product_id, title=row.title, category=row.category, stock_qty=row.stock_qty)
        for row in selected
    ]


async def build_daily_qty_series(
    session,
    history_days: int,
    include_categories: list[str] | None,
) -> dict[str, list[float]]:
    products = await list_products(session, include_categories)
    if not products:
        return {}

    end_dt = utcnow()
    end_day = end_dt.date()
    start_day = end_day - timedelta(days=history_days - 1)
    start_dt = datetime.combine(start_day, datetime.min.time(), tzinfo=end_dt.tzinfo)

    product_ids = [product.product_id for product in products]
    paid_filter = or_(OwnerbotDemoOrder.status == "paid", OwnerbotDemoOrder.payment_status == "paid")

    stmt = (
        select(
            OwnerbotDemoOrderItem.product_id,
            func.date(OwnerbotDemoOrder.created_at).label("sale_day"),
            func.sum(OwnerbotDemoOrderItem.qty).label("daily_qty"),
        )
        .join(OwnerbotDemoOrder, OwnerbotDemoOrder.order_id == OwnerbotDemoOrderItem.order_id)
        .where(
            and_(
                OwnerbotDemoOrderItem.product_id.in_(product_ids),
                OwnerbotDemoOrder.created_at >= start_dt,
                OwnerbotDemoOrder.created_at <= end_dt,
                paid_filter,
            )
        )
        .group_by(OwnerbotDemoOrderItem.product_id, func.date(OwnerbotDemoOrder.created_at))
    )

    rows = (await session.execute(stmt)).all()
    day_index = _day_index(start_day, history_days)
    series_map: dict[str, list[float]] = {product_id: [0.0] * history_days for product_id in product_ids}

    for row in rows:
        idx = day_index.get(_coerce_date(row.sale_day))
        if idx is None:
            continue
        series_map[row.product_id][idx] = float(row.daily_qty or 0.0)

    return series_map


def _day_index(start_day: date, history_days: int) -> dict[date, int]:
    return {start_day + timedelta(days=offset): offset for offset in range(history_days)}


def _coerce_date(value: object) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str):
        return date.fromisoformat(value)
    return None


def forecast_sma(series: Iterable[float], window_days: int) -> float:
    values = [float(value) for value in series]
    if not values:
        return 0.0
    window = values[-window_days:] if len(values) >= window_days else values
    return float(sum(window) / len(window)) if window else 0.0


def forecast_ses(series: Iterable[float], alpha: float) -> float:
    values = [float(value) for value in series]
    if not values:
        return 0.0

    level = values[0]
    for value in values[1:]:
        level = alpha * value + (1.0 - alpha) * level
    return float(level)


def confidence_from(series: Iterable[float], history_days: int) -> str:
    nonzero_days = sum(1 for value in series if float(value) > 0)
    if history_days >= 30 and nonzero_days >= 10:
        return "HIGH"
    if history_days >= 14 and nonzero_days >= 5:
        return "MED"
    return "LOW"
