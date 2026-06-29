"""Fetch TAO market price and subnet registration economics."""

from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Any

import httpx

from app.config import Settings, get_settings

logger = logging.getLogger(__name__)

RAO_PER_TAO = 1_000_000_000


@dataclass
class _CacheEntry:
    value: Any
    expires_at: float


_price_cache: _CacheEntry | None = None
_subnet_cache: dict[int, _CacheEntry] = {}


def _utcnow() -> datetime:
    return datetime.now(timezone.utc)


async def fetch_tao_price_usd(settings: Settings | None = None) -> tuple[float | None, str | None, datetime | None]:
    """Return (usd_price, source_label, updated_at). CoinGecko first; optional TMC if configured."""
    settings = settings or get_settings()
    global _price_cache

    now = time.monotonic()
    if _price_cache and _price_cache.expires_at > now:
        usd, source, updated = _price_cache.value
        return usd, source, updated

    usd: float | None = None
    source: str | None = None
    updated = _utcnow()

    if settings.taomarketcap_api_key and settings.taomarketcap_price_url:
        try:
            headers = {"Authorization": f"Bearer {settings.taomarketcap_api_key}"}
            async with httpx.AsyncClient(timeout=settings.market_http_timeout_seconds) as client:
                resp = await client.get(settings.taomarketcap_price_url, headers=headers)
                resp.raise_for_status()
                data = resp.json()
                usd = _parse_tmc_price(data)
                if usd is not None:
                    source = "taomarketcap"
        except Exception:
            logger.warning("taomarketcap price fetch failed", exc_info=True)

    if usd is None:
        try:
            async with httpx.AsyncClient(timeout=settings.market_http_timeout_seconds) as client:
                resp = await client.get(
                    settings.coingecko_tao_price_url,
                    params={"ids": "bittensor", "vs_currencies": "usd"},
                )
                resp.raise_for_status()
                data = resp.json()
                usd = float(data["bittensor"]["usd"])
                source = "coingecko"
        except Exception:
            logger.warning("coingecko price fetch failed", exc_info=True)
            return None, None, None

    _price_cache = _CacheEntry((usd, source, updated), now + settings.market_price_cache_seconds)
    return usd, source, updated


def _parse_tmc_price(data: dict[str, Any]) -> float | None:
    """Best-effort parser for TaoMarketCap price payloads."""
    for key in ("price", "usd", "price_usd", "tao_price"):
        if key in data and data[key] is not None:
            return float(data[key])
    if "data" in data and isinstance(data["data"], dict):
        return _parse_tmc_price(data["data"])
    return None


async def fetch_subnet_economics(
    netuid: int,
    settings: Settings | None = None,
) -> dict[str, Any]:
    """On-chain registration burn and alpha price for a subnet."""
    settings = settings or get_settings()
    now = time.monotonic()
    cached = _subnet_cache.get(netuid)
    if cached and cached.expires_at > now:
        return cached.value

    from bittensor.core.async_subtensor import AsyncSubtensor

    result: dict[str, Any] = {
        "registration_burn_tao": None,
        "alpha_price_tao": None,
        "chain_block": None,
    }

    try:
        async with AsyncSubtensor(network=settings.bittensor_network) as st:
            info = await st.get_subnet_info(netuid)
            if info and getattr(info, "burn", None) is not None:
                result["registration_burn_tao"] = float(info.burn.tao)
            try:
                alpha = await st.get_subnet_price(netuid)
                if alpha is not None:
                    result["alpha_price_tao"] = float(alpha.tao)
            except Exception:
                logger.debug("alpha price unavailable for SN%s", netuid, exc_info=True)
            result["chain_block"] = await st.get_current_block()
    except Exception:
        logger.warning("subnet economics fetch failed for SN%s", netuid, exc_info=True)

    _subnet_cache[netuid] = _CacheEntry(result, now + settings.market_subnet_cache_seconds)
    return result


async def build_market_overview(netuid: int, settings: Settings | None = None) -> dict[str, Any]:
    settings = settings or get_settings()
    usd, source, price_updated = await fetch_tao_price_usd(settings)
    econ = await fetch_subnet_economics(netuid, settings)

    burn_tao = econ.get("registration_burn_tao")
    burn_usd = (burn_tao * usd) if burn_tao is not None and usd is not None else None

    return {
        "subnet": netuid,
        "tao_price_usd": usd,
        "tao_price_source": source,
        "tao_price_updated_at": price_updated,
        "registration_burn_tao": burn_tao,
        "registration_burn_usd": burn_usd,
        "alpha_price_tao": econ.get("alpha_price_tao"),
        "chain_block": econ.get("chain_block"),
        "network": settings.bittensor_network,
        "fetched_at": _utcnow(),
    }
