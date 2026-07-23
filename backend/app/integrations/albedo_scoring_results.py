"""Fetch Albedo scoring-results.jsonl artifacts from Hippius S3."""

from __future__ import annotations

import json
import logging
import time
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_CACHE: dict[str, tuple[float, str]] = {}
_CACHE_TTL_SECONDS = 300.0


def scoring_results_url(eval_run: dict[str, Any]) -> str | None:
    artifacts = eval_run.get("artifacts") or {}
    url = artifacts.get("SCORING_RESULTS") or artifacts.get("scoring_results")
    return str(url) if url else None


def _cache_get(key: str) -> str | None:
    now = time.monotonic()
    cached = _CACHE.get(key)
    if cached and cached[0] > now:
        return cached[1]
    return None


def _cache_set(key: str, text: str) -> None:
    _CACHE[key] = (time.monotonic() + _CACHE_TTL_SECONDS, text)


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


def count_scoring_results_lines(text: str) -> int:
    return sum(1 for line in text.splitlines() if line.strip())


async def fetch_scoring_results_text(
    url: str,
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    fresh: bool = False,
) -> str:
    """Download raw scoring-results.jsonl text."""
    settings = settings or get_settings()
    if not fresh:
        cached = _cache_get(url)
        if cached is not None:
            return cached

    timeout = max(settings.market_http_timeout_seconds, 30.0)

    async def _do(c: httpx.AsyncClient) -> str:
        resp = await c.get(url)
        resp.raise_for_status()
        return resp.text

    try:
        if client is not None:
            text = await _do(client)
        else:
            async with httpx.AsyncClient(timeout=timeout) as c:
                text = await _do(c)
        if not fresh:
            _cache_set(url, text)
        return text
    except Exception:
        logger.warning("Albedo scoring-results fetch failed url=%s", url, exc_info=True)
        raise


async def fetch_scoring_results_jsonl(
    url: str,
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
    fresh: bool = False,
) -> list[dict[str, Any]]:
    """Download and parse a scoring-results.jsonl artifact."""
    text = await fetch_scoring_results_text(
        url,
        settings=settings,
        client=client,
        fresh=fresh,
    )
    return parse_scoring_results_jsonl(text)
