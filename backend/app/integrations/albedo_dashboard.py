"""Fetch Albedo subnet dashboard JSON from albedo.tech."""

from __future__ import annotations

import logging
import time
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, dict[str, Any]]] = {}
_CACHE_TTL_SECONDS = 30
_LIVE_CACHE_TTL_SECONDS = 8


def _cache_get(key: str) -> dict[str, Any] | None:
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached and cached[0] > now:
        return cached[1]
    return None


def _cache_set(key: str, payload: dict[str, Any], ttl: float) -> None:
    _CACHE[key] = (time.monotonic() + ttl, payload)


async def fetch_albedo_json(
    path: str,
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    live: bool = False,
    fresh: bool = False,
) -> dict[str, Any]:
    """Fetch a JSON document from the Albedo dashboard (albedo.tech)."""
    settings = settings or get_settings()
    base = settings.albedo_dashboard_url.rstrip("/")
    url = f"{base}/{path.lstrip('/')}"
    ttl = _LIVE_CACHE_TTL_SECONDS if live else _CACHE_TTL_SECONDS
    cache_key = f"{url}|ttl={ttl}"

    if not fresh:
        cached = _cache_get(cache_key)
        if cached is not None:
            return cached

    timeout = settings.market_http_timeout_seconds

    async def _do(c: httpx.AsyncClient) -> dict[str, Any]:
        resp = await c.get(url)
        resp.raise_for_status()
        payload = resp.json()
        if not isinstance(payload, dict):
            raise ValueError(f"Expected JSON object from {url}")
        return payload

    try:
        if client is not None:
            result = await _do(client)
        else:
            async with httpx.AsyncClient(timeout=timeout) as c:
                result = await _do(c)
        if not fresh:
            _cache_set(cache_key, result, ttl)
        return result
    except Exception:
        logger.warning("Albedo dashboard fetch failed url=%s", url, exc_info=True)
        raise


async def fetch_dashboard(
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    live: bool = False,
    fresh: bool = False,
) -> dict[str, Any]:
    return await fetch_albedo_json(
        "data/dashboard.json",
        settings=settings,
        client=client,
        live=live,
        fresh=fresh,
    )


async def fetch_state(
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    live: bool = False,
    fresh: bool = False,
) -> dict[str, Any]:
    return await fetch_albedo_json(
        "data/state.json",
        settings=settings,
        client=client,
        live=live,
        fresh=fresh,
    )
