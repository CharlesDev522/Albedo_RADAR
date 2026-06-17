"""Fetch Quasar SN24 status from the public validator API."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_CACHE: dict[str, Any] = {"fetched_at": 0.0, "raw": None}
_CACHE_TTL_SECONDS = 4.0


async def fetch_quasar_dashboard() -> dict[str, Any] | None:
    settings = get_settings()
    now = time.monotonic()
    if _CACHE["raw"] is not None and now - _CACHE["fetched_at"] < _CACHE_TTL_SECONDS:
        return _CACHE["raw"]

    url = settings.quasar_dashboard_url
    headers = {"Cache-Control": "no-cache", "Pragma": "no-cache"}
    buster = int(time.time() * 1000)
    try:
        async with httpx.AsyncClient(timeout=25.0, headers=headers) as client:
            resp = await client.get(f"{url}?t={buster}")
            if resp.status_code != 200:
                logger.warning("quasar dashboard HTTP %s", resp.status_code)
                return _CACHE["raw"]
            data = resp.json()
            if not isinstance(data, dict):
                return _CACHE["raw"]
            _CACHE["raw"] = data
            _CACHE["fetched_at"] = now
            return data
    except Exception:
        logger.warning("quasar dashboard fetch failed", exc_info=True)
        return _CACHE["raw"]
