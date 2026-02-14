from __future__ import annotations

import asyncio
import time
from typing import Any

import httpx

from app.core.audit import write_audit_event
from app.core.settings import Settings


class SisActionsClient:
    def __init__(self, settings: Settings) -> None:
        self._settings = settings
        self._base_url = settings.sis_base_url.rstrip("/")
        self._headers = {"X-OWNERBOT-KEY": settings.sis_ownerbot_api_key} if settings.sis_ownerbot_api_key else {}

    def _build_headers(self, *, correlation_id: str, extra_headers: dict[str, str] | None = None) -> dict[str, str]:
        headers = dict(self._headers)
        headers["X-CORRELATION-ID"] = correlation_id
        if extra_headers:
            headers.update(extra_headers)
        return headers

    async def _request_json(
        self,
        method: str,
        path: str,
        *,
        correlation_id: str,
        payload: dict[str, Any] | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any] | None]:
        url = f"{self._base_url}{path}"
        headers = self._build_headers(correlation_id=correlation_id, extra_headers=extra_headers)
        retries = max(self._settings.sis_max_retries, 0)
        backoff = self._settings.sis_retry_backoff_base_sec

        for attempt in range(retries + 1):
            start = time.perf_counter()
            await write_audit_event("upstream_call_started", {"endpoint": path}, correlation_id=correlation_id)
            try:
                async with httpx.AsyncClient(timeout=self._settings.sis_timeout_sec, headers=headers) as client:
                    resp = await client.request(method, url, json=payload)
                latency_ms = int((time.perf_counter() - start) * 1000)
                await write_audit_event(
                    "upstream_call_finished",
                    {"endpoint": path, "latency_ms": latency_ms, "status": resp.status_code, "correlation_id": correlation_id},
                    correlation_id=correlation_id,
                )
                if resp.status_code in {429, 500, 502, 503, 504} and attempt < retries:
                    await asyncio.sleep(backoff * (2**attempt))
                    continue
                try:
                    body = resp.json()
                except ValueError:
                    body = None
                return resp.status_code, body
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
                return 0, None

        return 0, None

    async def post_action(
        self,
        path: str,
        payload: dict[str, Any],
        *,
        correlation_id: str,
        idempotency_key: str | None = None,
        extra_headers: dict[str, str] | None = None,
    ) -> tuple[int, dict[str, Any] | None]:
        headers = dict(extra_headers or {})
        if idempotency_key:
            headers["Idempotency-Key"] = idempotency_key
        return await self._request_json("POST", path, correlation_id=correlation_id, payload=payload, extra_headers=headers or None)

    async def get_action(self, path: str, *, correlation_id: str) -> tuple[int, dict[str, Any] | None]:
        return await self._request_json("GET", path, correlation_id=correlation_id)

    async def patch_action(self, path: str, payload: dict[str, Any], *, correlation_id: str) -> tuple[int, dict[str, Any] | None]:
        return await self._request_json("PATCH", path, correlation_id=correlation_id, payload=payload)
