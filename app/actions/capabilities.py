from __future__ import annotations

import json
from dataclasses import dataclass
from datetime import datetime
from typing import Any, Literal

from app.core.redis import get_redis, get_test_redis
from app.core.time import utcnow
from app.core.settings import Settings
from app.upstream.sis_actions_client import SisActionsClient

CapabilityKey = Literal[
    "fx",
    "prices_bump",
    "prices_rollback",
    "discounts",
    "products_publish",
    "looks_publish",
]

CACHE_TTL_SECONDS = 6 * 60 * 60
_CACHE_PREFIX = "ownerbot:sis:capabilities"


@dataclass(frozen=True)
class CapabilityProbe:
    key: CapabilityKey
    method: Literal["GET", "POST", "PATCH"]
    endpoint: str
    payload: dict[str, Any] | None = None


CAPABILITY_PROBES: tuple[CapabilityProbe, ...] = (
    CapabilityProbe(key="fx", method="GET", endpoint="/fx/status"),
    CapabilityProbe(key="prices_bump", method="POST", endpoint="/prices/bump/preview", payload={}),
    CapabilityProbe(key="prices_rollback", method="POST", endpoint="/reprice/rollback/preview", payload={}),
    CapabilityProbe(key="discounts", method="POST", endpoint="/discounts/set/preview", payload={}),
    CapabilityProbe(key="products_publish", method="POST", endpoint="/products/publish/preview", payload={}),
    CapabilityProbe(key="looks_publish", method="POST", endpoint="/looks/publish/preview", payload={}),
)

TOOL_CAPABILITIES: dict[str, tuple[CapabilityKey, ...]] = {
    "sis_fx_reprice": ("fx",),
    "sis_fx_reprice_auto": ("fx",),
    "sis_fx_settings_update": ("fx",),
    "sis_fx_status": ("fx",),
    "sis_fx_rollback": ("prices_rollback",),
    "sis_prices_bump": ("prices_bump",),
    "sis_discounts_set": ("discounts",),
    "sis_discounts_clear": ("discounts",),
    "sis_products_publish": ("products_publish",),
    "sis_looks_publish": ("looks_publish",),
}

ENDPOINT_CAPABILITIES: tuple[tuple[str, CapabilityKey], ...] = (
    ("/fx/", "fx"),
    ("/prices/bump/", "prices_bump"),
    ("/reprice/rollback/", "prices_rollback"),
    ("/discounts/", "discounts"),
    ("/products/publish/", "products_publish"),
    ("/looks/publish/", "looks_publish"),
)


def required_capabilities_for_tool(tool_name: str) -> tuple[CapabilityKey, ...]:
    return TOOL_CAPABILITIES.get(tool_name, ())


def capability_for_endpoint(path: str) -> CapabilityKey | None:
    for prefix, key in ENDPOINT_CAPABILITIES:
        if path.startswith(prefix):
            return key
    return None


def _cache_key(scope: str) -> str:
    return f"{_CACHE_PREFIX}:{scope}"


def _scope_from_payload(payload: dict[str, Any] | None) -> str:
    if isinstance(payload, dict) and payload.get("shop_id") is not None:
        return f"shop:{payload['shop_id']}"
    return "shop:default"


def _parse_cached(raw: str | None) -> dict[str, Any] | None:
    if not raw:
        return None
    try:
        value = json.loads(raw)
    except (TypeError, ValueError):
        return None
    return value if isinstance(value, dict) else None


async def _probe_one(client: SisActionsClient, probe: CapabilityProbe, correlation_id: str) -> dict[str, Any]:
    if probe.method == "GET":
        status_code, _ = await client.get_action(probe.endpoint, correlation_id=correlation_id)
    elif probe.method == "PATCH":
        status_code, _ = await client.patch_action(probe.endpoint, probe.payload or {}, correlation_id=correlation_id)
    else:
        status_code, _ = await client.post_action(probe.endpoint, probe.payload or {}, correlation_id=correlation_id)

    if status_code == 404:
        supported: bool | None = False
        status = "unsupported"
    elif status_code in {401, 403}:
        supported = None
        status = "misconfigured"
    elif status_code in {200, 422}:
        supported = True
        status = "supported"
    elif status_code == 0:
        supported = None
        status = "offline"
    else:
        supported = None
        status = "unknown"

    return {
        "supported": supported,
        "status": status,
        "status_code": status_code,
        "endpoint": probe.endpoint,
        "method": probe.method,
    }


async def probe_sis_capabilities(*, settings: Settings, correlation_id: str) -> dict[str, Any]:
    client = SisActionsClient(settings)
    capabilities: dict[str, Any] = {}
    for probe in CAPABILITY_PROBES:
        capabilities[probe.key] = await _probe_one(client, probe, correlation_id)
    return {
        "checked_at": utcnow().isoformat(),
        "capabilities": capabilities,
    }


async def get_sis_capabilities(
    *,
    settings: Settings,
    correlation_id: str,
    payload_scope: dict[str, Any] | None = None,
    force_refresh: bool = False,
) -> dict[str, Any]:
    scope = _scope_from_payload(payload_scope)
    key = _cache_key(scope)
    try:
        redis = await get_redis()
    except RuntimeError:
        redis = await get_test_redis()

    if not force_refresh:
        cached = _parse_cached(await redis.get(key))
        if cached is not None:
            return cached

    probed = await probe_sis_capabilities(settings=settings, correlation_id=correlation_id)
    await redis.set(key, json.dumps(probed), ex=CACHE_TTL_SECONDS)
    return probed


def capability_support_status(capabilities_report: dict[str, Any], key: CapabilityKey) -> bool | None:
    capabilities = capabilities_report.get("capabilities") if isinstance(capabilities_report, dict) else None
    if not isinstance(capabilities, dict):
        return None
    item = capabilities.get(key)
    if not isinstance(item, dict):
        return None
    value = item.get("supported")
    if value is None:
        return None
    return bool(value)


def checked_at_dt(capabilities_report: dict[str, Any]) -> datetime | None:
    checked_at = capabilities_report.get("checked_at") if isinstance(capabilities_report, dict) else None
    if not isinstance(checked_at, str):
        return None
    try:
        return datetime.fromisoformat(checked_at)
    except ValueError:
        return None
