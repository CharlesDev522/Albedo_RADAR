"""Fetch Albedo SN97 king-of-the-hill status from the Hippius dashboard API."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config import get_settings

logger = logging.getLogger(__name__)

_CACHE: dict[str, Any] = {"fetched_at": 0.0, "data": None}
_CACHE_TTL_SECONDS = 15.0


async def fetch_albedo_dashboard(*, force: bool = False) -> dict[str, Any] | None:
    """Return parsed dashboard.json or None on failure."""
    settings = get_settings()
    url = settings.albedo_dashboard_url
    now = time.monotonic()
    if (
        not force
        and _CACHE["data"] is not None
        and now - float(_CACHE["fetched_at"]) < _CACHE_TTL_SECONDS
    ):
        return _CACHE["data"]

    try:
        async with httpx.AsyncClient(timeout=20.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            data = resp.json()
    except Exception:
        logger.warning("albedo dashboard fetch failed url=%s", url, exc_info=True)
        return _CACHE["data"]

    _CACHE["fetched_at"] = now
    _CACHE["data"] = data
    return data


def king_hotkey(dashboard: dict[str, Any] | None) -> str | None:
    if not dashboard:
        return None
    king = dashboard.get("king") or {}
    hotkey = king.get("hotkey")
    return str(hotkey) if hotkey else None


def king_uid(dashboard: dict[str, Any] | None) -> int | None:
    if not dashboard:
        return None
    uid = (dashboard.get("king") or {}).get("uid")
    return int(uid) if uid is not None else None
