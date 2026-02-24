from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any


@dataclass(frozen=True)
class ActionCoercionResult:
    payload: dict[str, Any]
    missing_fields: tuple[str, ...] = ()

    @property
    def ok(self) -> bool:
        return not self.missing_fields

    def missing_prompt(self) -> str:
        return f"Нужно уточнить: {', '.join(self.missing_fields)}."


def _to_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    if isinstance(value, str):
        digits = re.sub(r"\D+", "", value)
        if digits:
            return int(digits)
    return None


def _to_float(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, (int, float)):
        return float(value)
    if isinstance(value, str):
        cleaned = value.strip().replace("%", "").replace(",", ".")
        try:
            return float(cleaned)
        except ValueError:
            return None
    return None


def _to_hours(value: Any) -> int | None:
    if isinstance(value, int):
        return value if value > 0 else None
    if isinstance(value, str):
        match = re.search(r"(\d{1,3})\s*(h|hr|hrs|hour|hours|ч|час|часа|часов)?", value.lower())
        if match:
            hours = int(match.group(1))
            return hours if hours > 0 else None
    return None


def _to_product_ids(value: Any) -> list[str]:
    if isinstance(value, list):
        items = value
    else:
        items = re.split(r"[\s,;]+", str(value or ""))
    out: list[str] = []
    for item in items:
        candidate = str(item).strip()
        if not candidate:
            continue
        number = _to_int(candidate)
        out.append(str(number) if number is not None else candidate)
    return out


def _coerce_prices_bump(payload: dict[str, Any]) -> ActionCoercionResult:
    out: dict[str, Any] = {"dry_run": True}
    raw = payload.get("bump_percent", payload.get("value"))
    pct = _to_float(raw)
    if pct is None:
        return ActionCoercionResult(payload=out, missing_fields=("процент изменения цены",))
    pct = max(0.1, min(95.0, abs(pct)))
    out["bump_percent"] = f"{pct:.2f}".rstrip("0").rstrip(".")
    if "rounding_mode" in payload:
        out["rounding_mode"] = payload.get("rounding_mode")
    return ActionCoercionResult(payload=out)


def _coerce_create_coupon(payload: dict[str, Any]) -> ActionCoercionResult:
    out: dict[str, Any] = {"dry_run": True}
    if payload.get("code"):
        out["code"] = str(payload["code"]).strip().upper()
    pct = _to_float(payload.get("percent_off"))
    if pct is None:
        pct = _to_float(payload.get("discount_percent"))
    if pct is None:
        return ActionCoercionResult(payload=out, missing_fields=("размер скидки в %",))
    out["percent_off"] = int(max(1, min(95, round(pct))))
    if payload.get("max_uses") is not None:
        max_uses = _to_int(payload.get("max_uses"))
        if max_uses is not None:
            out["max_uses"] = max_uses
    hours_raw = payload.get("hours_valid", payload.get("duration"))
    hours = _to_hours(hours_raw) if hours_raw is not None else None
    if hours is not None:
        out["hours_valid"] = hours
    if not out.get("code"):
        out["code"] = f"AUTO{out['percent_off']}"
    return ActionCoercionResult(payload=out)


def _coerce_notify_team(payload: dict[str, Any]) -> ActionCoercionResult:
    out: dict[str, Any] = {"dry_run": True}
    message = payload.get("message")
    if not message and payload.get("order_id"):
        message = f"Проверьте заказ {payload['order_id']}"
    if not message:
        return ActionCoercionResult(payload=out, missing_fields=("сообщение для менеджера",))
    out["message"] = str(message).strip()
    order_id = _to_int(payload.get("order_id"))
    if order_id is not None and str(order_id) not in out["message"]:
        out["message"] = f"{out['message']} (order {order_id})"
    return ActionCoercionResult(payload=out)


def _coerce_products_publish(payload: dict[str, Any], *, target_status: str) -> ActionCoercionResult:
    out: dict[str, Any] = {"dry_run": True, "target_status": target_status}
    product_ids = _to_product_ids(payload.get("product_ids"))
    if not product_ids:
        return ActionCoercionResult(payload=out, missing_fields=("список product_ids",))
    out["product_ids"] = product_ids
    return ActionCoercionResult(payload=out)


def _coerce_fx_reprice_auto(payload: dict[str, Any]) -> ActionCoercionResult:
    out = {"dry_run": True}
    if payload.get("force") is not None:
        out["force"] = bool(payload.get("force"))
    if payload.get("refresh_snapshot") is not None:
        out["refresh_snapshot"] = bool(payload.get("refresh_snapshot"))
    return ActionCoercionResult(payload=out)


COERCERS = {
    "sis_fx_reprice_auto": _coerce_fx_reprice_auto,
    "sis_prices_bump": _coerce_prices_bump,
    "create_coupon": _coerce_create_coupon,
    "notify_team": _coerce_notify_team,
    "sis_products_publish": lambda payload: _coerce_products_publish(payload, target_status=str((payload or {}).get("target_status") or "ACTIVE")),
}


def coerce_action_payload(tool_name: str, payload: dict[str, Any] | None) -> ActionCoercionResult:
    payload_dict = dict(payload or {})
    coerce = COERCERS.get(tool_name)
    if coerce is None:
        return ActionCoercionResult(payload={"dry_run": True})
    result = coerce(payload_dict)
    result.payload["dry_run"] = True
    return result
