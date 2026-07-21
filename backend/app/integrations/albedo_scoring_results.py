"""Fetch Albedo scoring-results.jsonl artifacts from Hippius S3."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, list[dict[str, Any]]]] = {}
_CACHE_TTL_SECONDS = 300.0


def _cache_get(key: str) -> list[dict[str, Any]] | None:
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached and cached[0] > now:
        return cached[1]
    return None


def _cache_set(key: str, rows: list[dict[str, Any]]) -> None:
    _CACHE[key] = (time.monotonic() + _CACHE_TTL_SECONDS, rows)


def parse_scoring_results_jsonl(text: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_no, line in enumerate(text.splitlines(), start=1):
        stripped = line.strip()
        if not stripped:
            continue
        obj = json.loads(stripped)
        if not isinstance(obj, dict):
            raise ValueError(f"Line {line_no}: expected JSON object")
        rows.append(obj)
    return rows


async def fetch_scoring_results_jsonl(
    url: str,
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    fresh: bool = False,
) -> list[dict[str, Any]]:
    """Download and parse a scoring-results.jsonl artifact."""
    settings = settings or get_settings()
    if not fresh:
        cached = _cache_get(url)
        if cached is not None:
            return cached

    timeout = max(settings.market_http_timeout_seconds, 30.0)

    async def _do(c: httpx.AsyncClient) -> list[dict[str, Any]]:
        resp = await c.get(url)
        resp.raise_for_status()
        return parse_scoring_results_jsonl(resp.text)

    try:
        if client is not None:
            rows = await _do(client)
        else:
            async with httpx.AsyncClient(timeout=timeout) as c:
                rows = await _do(c)
        if not fresh:
            _cache_set(url, rows)
        return rows
    except Exception:
        logger.warning("Albedo scoring-results fetch failed url=%s", url, exc_info=True)
        raise
