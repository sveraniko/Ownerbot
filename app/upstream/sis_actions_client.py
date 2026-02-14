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

    async def post_action(self, path: str, payload: dict[str, Any], *, correlation_id: str) -> tuple[int, dict[str, Any] | None]:
        url = f"{self._base_url}{path}"
        retries = max(self._settings.sis_max_retries, 0)
        backoff = self._settings.sis_retry_backoff_base_sec

        for attempt in range(retries + 1):
            start = time.perf_counter()
            await write_audit_event("upstream_call_started", {"endpoint": path}, correlation_id=correlation_id)
            try:
                async with httpx.AsyncClient(timeout=self._settings.sis_timeout_sec, headers=self._headers) as client:
                    resp = await client.post(url, json=payload)
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
