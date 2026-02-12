from __future__ import annotations

from io import BytesIO
from typing import Any

import matplotlib

matplotlib.use("Agg")

import matplotlib.pyplot as plt


def _extract_value(item: dict[str, Any], keys: tuple[str, ...], fallback: float = 0.0) -> float:
    for key in keys:
        if key in item and item[key] is not None:
            return float(item[key])
    return fallback


def render_revenue_trend_png(series: list[dict], currency: str, title: str, tz: str | None) -> bytes:
    dates = [str(item.get("day") or item.get("date") or "") for item in series]
    revenue = [_extract_value(item, ("revenue_gross",)) for item in series]
    orders_paid = [_extract_value(item, ("orders_paid",), fallback=0.0) for item in series]

    fig, ax1 = plt.subplots(figsize=(12, 6), constrained_layout=True)
    ax1.plot(dates, revenue, color="#2E86C1", linewidth=2.0, marker="o", label=f"Revenue ({currency})")
    ax1.set_xlabel("Date")
    ax1.set_ylabel(f"Revenue ({currency})", color="#2E86C1")
    ax1.tick_params(axis="y", labelcolor="#2E86C1")
    ax1.grid(alpha=0.3, linestyle="--")
    ax1.set_title(title)

    ax2 = ax1.twinx()
    ax2.plot(dates, orders_paid, color="#E67E22", linewidth=1.8, marker="s", label="Orders paid")
    ax2.set_ylabel("Orders paid", color="#E67E22")
    ax2.tick_params(axis="y", labelcolor="#E67E22")

    fig.autofmt_xdate(rotation=30, ha="right")

    lines1, labels1 = ax1.get_legend_handles_labels()
    lines2, labels2 = ax2.get_legend_handles_labels()
    ax1.legend(lines1 + lines2, labels1 + labels2, loc="upper left")

    if tz:
        fig.text(0.99, 0.01, f"TZ: {tz}", ha="right", va="bottom", fontsize=8, alpha=0.7)

    output = BytesIO()
    fig.savefig(output, format="png", dpi=160)
    plt.close(fig)
    return output.getvalue()
