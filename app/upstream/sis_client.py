from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.core.audit import write_audit_event
from app.core.settings import Settings
from app.tools.contracts import ToolProvenance, ToolResponse


class SisClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.sis_base_url.rstrip("/")
        self._headers = {"X-API-Key": settings.sis_ownerbot_api_key} if settings.sis_ownerbot_api_key else {}

    async def ping(self, correlation_id: str) -> ToolResponse:
        return await self._request("GET", "/ownerbot/v1/ping", correlation_id=correlation_id)

    async def kpi_summary(self, *, from_date: str | None, to_date: str | None, tz: str, correlation_id: str) -> ToolResponse:
        params = {"from": from_date, "to": to_date, "tz": tz}
        return await self._request("GET", "/ownerbot/v1/kpi/summary", params=params, correlation_id=correlation_id)

    async def revenue_trend(self, *, from_date: str | None, to_date: str | None, tz: str, correlation_id: str) -> ToolResponse:
        params = {"from": from_date, "to": to_date, "tz": tz}
        return await self._request("GET", "/ownerbot/v1/revenue/trend", params=params, correlation_id=correlation_id)

    async def orders_search(self, *, q: str | None, limit: int | None, correlation_id: str) -> ToolResponse:
        params = {"q": q, "limit": limit}
        return await self._request("GET", "/ownerbot/v1/orders/search", params=params, correlation_id=correlation_id)

    async def order_detail(self, *, order_id: str, correlation_id: str) -> ToolResponse:
        return await self._request("GET", f"/ownerbot/v1/orders/{order_id}", correlation_id=correlation_id)

    async def _request(self, method: str, path: str, *, params: dict[str, Any] | None = None, correlation_id: str) -> ToolResponse:
        url = f"{self._base_url}{path}"
        retries = max(self._settings.sis_max_retries, 0)
        backoff = self._settings.sis_retry_backoff_base_sec

        for attempt in range(retries + 1):
            start = time.perf_counter()
            await write_audit_event("upstream_call_started", {"endpoint": path}, correlation_id=correlation_id)
            try:
                async with httpx.AsyncClient(timeout=self._settings.sis_timeout_sec, headers=self._headers) as client:
                    resp = await client.request(method, url, params={k: v for k, v in (params or {}).items() if v is not None})
                latency_ms = int((time.perf_counter() - start) * 1000)
                await write_audit_event(
                    "upstream_call_finished",
                    {"endpoint": path, "latency_ms": latency_ms, "status": resp.status_code, "correlation_id": correlation_id},
                    correlation_id=correlation_id,
                )

                if resp.status_code >= 400:
                    if resp.status_code == 429 or 500 <= resp.status_code <= 599:
                        if attempt < retries:
                            await asyncio.sleep(backoff * (2**attempt))
                            continue
                    return ToolResponse.fail(
                        correlation_id=correlation_id,
                        code="UPSTREAM_UNAVAILABLE",
                        message=f"SIS error status {resp.status_code}.",
                    )

                payload = resp.json()
                return _parse_envelope(payload, correlation_id)
            except httpx.HTTPError:
                latency_ms = int((time.perf_counter() - start) * 1000)
                await write_audit_event(
                    "upstream_call_finished",
                    {"endpoint": path, "latency_ms": latency_ms, "status": "network_error", "correlation_id": correlation_id},
                    correlation_id=correlation_id,
                )
                if attempt < retries:
                    await asyncio.sleep(backoff * (2**attempt))
                    continue
                return ToolResponse.fail(correlation_id=correlation_id, code="UPSTREAM_UNAVAILABLE", message="SIS upstream is unavailable.")
            except ValueError:
                return ToolResponse.fail(correlation_id=correlation_id, code="UPSTREAM_UNAVAILABLE", message="Invalid SIS JSON envelope.")

        return ToolResponse.fail(correlation_id=correlation_id, code="UPSTREAM_UNAVAILABLE", message="SIS upstream is unavailable.")


def _parse_envelope(payload: dict[str, Any], correlation_id: str) -> ToolResponse:
    if not isinstance(payload, dict):
        return ToolResponse.fail(correlation_id=correlation_id, code="PROVENANCE_INCOMPLETE", message="Envelope is not an object.")
    provenance = payload.get("provenance")
    if not isinstance(provenance, dict) or "sources" not in provenance or "filters_hash" not in provenance:
        return ToolResponse.fail(correlation_id=correlation_id, code="PROVENANCE_INCOMPLETE", message="SIS provenance is incomplete.")
    if "as_of" not in payload or "data" not in payload:
        return ToolResponse.fail(correlation_id=correlation_id, code="PROVENANCE_INCOMPLETE", message="SIS envelope is incomplete.")

    # Ensure window has required scope and type fields
    raw_window = provenance.get("window") or {}
    if not isinstance(raw_window, dict):
        raw_window = {}
    window = {
        "scope": raw_window.get("scope", "snapshot"),
        "type": raw_window.get("type", "snapshot"),
        **{k: v for k, v in raw_window.items() if k not in ("scope", "type")},
    }

    return ToolResponse.ok(
        correlation_id=correlation_id,
        data=payload.get("data") or {},
        provenance=ToolProvenance(
            sources=[str(v) for v in provenance.get("sources") or []],
            window=window,
            filters_hash=provenance.get("filters_hash"),
        ),
    )
