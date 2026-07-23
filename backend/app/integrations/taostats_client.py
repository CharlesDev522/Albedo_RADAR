"""TaoStats API client for metagraph reward fields."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

_CACHE: dict[tuple[int, int], tuple[float, Any]] = {}
_CACHE_TTL_SECONDS = 45


@dataclass(frozen=True)
class TaoStatsChampion:
    uid: int
    hotkey: str
    coldkey: str | None
    incentive: float
    emission_rao_per_epoch: float
    daily_reward_rao: float
    block_number: int | None
    timestamp: str | None


def _parse_float(value: Any) -> float:
    if value is None:
        return 0.0
    try:
        return float(value)
    except (TypeError, ValueError):
        return 0.0


async def fetch_champion_from_taostats(
    netuid: int,
    *,
    settings: Settings | None = None,
    client: httpx.AsyncClient | None = None,
) -> TaoStatsChampion | None:
    """Return top-incentive miner from TaoStats metagraph (matches their daily reward column)."""
    settings = settings or get_settings()
    api_key = settings.taostats_api_key
    if not api_key:
        return None

    cache_key = (netuid, 0)
    now = time.monotonic()
    cached = _CACHE.get(cache_key)
    if cached and cached[0] > now:
        return cached[1]

    base = settings.taostats_api_url.rstrip("/")
    url = f"{base}/api/metagraph/latest/v1"
    params = {"netuid": str(netuid), "limit": "256", "order": "incentive_desc"}
    headers = {"Authorization": api_key, "accept": "application/json"}
    timeout = settings.market_http_timeout_seconds

    async def _do(c: httpx.AsyncClient) -> TaoStatsChampion | None:
        resp = await c.get(url, params=params, headers=headers)
        resp.raise_for_status()
        payload = resp.json()
        rows = payload.get("data") or []
        best: TaoStatsChampion | None = None
        for row in rows:
            if row.get("validator_permit"):
                continue
            incentive = _parse_float(row.get("incentive"))
            emission_rao = _parse_float(row.get("emission"))
            daily_reward_rao = _parse_float(row.get("daily_reward"))
            if incentive <= 0 and emission_rao <= 0 and daily_reward_rao <= 0:
                continue
            hotkey_obj = row.get("hotkey") or {}
            hotkey = hotkey_obj.get("ss58") if isinstance(hotkey_obj, dict) else str(hotkey_obj)
            coldkey_obj = row.get("coldkey") or {}
            coldkey = coldkey_obj.get("ss58") if isinstance(coldkey_obj, dict) else None
            candidate = TaoStatsChampion(
                uid=int(row.get("uid", -1)),
                hotkey=hotkey or "",
                coldkey=coldkey,
                incentive=incentive,
                emission_rao_per_epoch=emission_rao,
                daily_reward_rao=daily_reward_rao,
                block_number=int(row["block_number"]) if row.get("block_number") is not None else None,
                timestamp=row.get("timestamp"),
            )
            if best is None:
                best = candidate
                continue
            if candidate.incentive > best.incentive:
                best = candidate
            elif candidate.incentive == best.incentive and candidate.daily_reward_rao > best.daily_reward_rao:
                best = candidate
        return best

    try:
        if client is not None:
            result = await _do(client)
        else:
            async with httpx.AsyncClient(timeout=timeout) as c:
                result = await _do(c)
        _CACHE[cache_key] = (now + _CACHE_TTL_SECONDS, result)
        return result
    except Exception:
        logger.warning("TaoStats champion fetch failed netuid=%d", netuid, exc_info=True)
        return None
