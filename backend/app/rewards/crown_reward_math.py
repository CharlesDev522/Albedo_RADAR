"""Estimate cumulative king/crown rewards from slot tenure and weight share."""

from __future__ import annotations

from app.integrations.market_client import build_market_overview
from app.integrations.taostats_client import fetch_champion_from_taostats
from app.rewards.emission_math import (
    daily_alpha_from_daily_reward_rao,
    daily_alpha_from_emission_per_epoch,
    daily_tao_equivalent,
    daily_usd,
)
from app.schemas.albedo_analysis import AlbedoRewardBasis

DEFAULT_KING_WEIGHT_BPS = 2000  # 20% per reign slot (Albedo default)
HOURS_PER_DAY = 24.0


def weight_share(weight_bps: int) -> float:
    return max(weight_bps, 0) / 10_000.0


def hourly_subnet_alpha(daily_subnet_alpha: float) -> float:
    if daily_subnet_alpha <= 0:
        return 0.0
    return daily_subnet_alpha / HOURS_PER_DAY


def estimate_crown_alpha(
    slot_hours: float,
    *,
    weight_bps: int,
    daily_subnet_alpha: float,
) -> float:
    """Cumulative α earned while holding a reign slot."""
    if slot_hours <= 0 or daily_subnet_alpha <= 0:
        return 0.0
    return slot_hours * hourly_subnet_alpha(daily_subnet_alpha) * weight_share(weight_bps)


def ongoing_daily_alpha(*, weight_bps: int, daily_subnet_alpha: float) -> float:
    """Current daily α accrual rate for an active reign slot."""
    if daily_subnet_alpha <= 0:
        return 0.0
    return daily_subnet_alpha * weight_share(weight_bps)


async def fetch_crown_reward_basis(subnet: int, *, settings=None) -> AlbedoRewardBasis:
    """Subnet emission basis for crown reward estimates (TaoStats when available)."""
    taostats = await fetch_champion_from_taostats(subnet, settings=settings)
    market = await build_market_overview(subnet, settings=settings)
    alpha_price = market.get("alpha_price_tao")
    tao_usd = market.get("tao_price_usd")

    daily_subnet_alpha = 0.0
    source = "unavailable"
    note = (
        "Set TAOSTATS_API_KEY for live subnet emission. "
        "Crown reward = Σ slot_hours × (weight_bps/10000) × (daily_subnet_α / 24)."
    )

    if taostats is not None:
        champion_daily = daily_alpha_from_daily_reward_rao(taostats.daily_reward_rao)
        if champion_daily <= 0:
            champion_daily = daily_alpha_from_emission_per_epoch(taostats.emission_rao_per_epoch)
        if champion_daily > 0:
            if taostats.incentive > 0:
                daily_subnet_alpha = champion_daily / taostats.incentive
            else:
                daily_subnet_alpha = champion_daily
            source = "taostats"
            note = (
                f"Subnet daily α ≈ top miner daily α / incentive ({taostats.incentive:.4f}). "
                "Per crown: slot_hours × weight_share × (daily_subnet_α / 24). "
                f"Default weight {DEFAULT_KING_WEIGHT_BPS} bps when historical weight unknown."
            )

    daily_tao = daily_tao_equivalent(daily_subnet_alpha, alpha_price)
    daily_usd_val = daily_usd(daily_tao, tao_usd)

    return AlbedoRewardBasis(
        daily_subnet_alpha=round(daily_subnet_alpha, 4),
        alpha_price_tao=alpha_price,
        tao_price_usd=tao_usd,
        daily_subnet_tao=round(daily_tao, 6) if daily_tao is not None else None,
        daily_subnet_usd=round(daily_usd_val, 2) if daily_usd_val is not None else None,
        calculation_source=source,
        default_weight_bps=DEFAULT_KING_WEIGHT_BPS,
        note=note,
    )
