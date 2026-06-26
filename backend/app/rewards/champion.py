"""Build champion miner daily reward summary."""

from __future__ import annotations

from app.integrations.market_client import build_market_overview
from app.rewards.emission_math import (
    BLOCKS_PER_DAY,
    daily_alpha_from_emission_per_block,
    daily_tao_equivalent,
    daily_usd,
    emission_per_block_tao,
)
from app.schemas.incentives import ChampionReward, MinerIncentiveEntry


async def build_champion_reward(
    subnet: int,
    miners: list[MinerIncentiveEntry],
) -> ChampionReward | None:
    if not miners:
        return None

    champion = max(miners, key=lambda m: (m.incentive, -m.uid))
    if champion.incentive <= 0 and champion.emission <= 0:
        return None

    emission_rao = float(champion.emission or 0.0)
    daily_alpha = daily_alpha_from_emission_per_block(emission_rao)

    market = await build_market_overview(subnet)
    alpha_price = market.get("alpha_price_tao")
    tao_usd = market.get("tao_price_usd")
    daily_tao = daily_tao_equivalent(daily_alpha, alpha_price)
    daily_usd_val = daily_usd(daily_tao, tao_usd)

    return ChampionReward(
        uid=champion.uid,
        hotkey=champion.hotkey,
        coldkey=champion.coldkey,
        incentive=champion.incentive,
        emission_per_block_rao=emission_rao,
        emission_per_block_alpha=emission_per_block_tao(emission_rao),
        daily_alpha=daily_alpha,
        daily_tao_equivalent=daily_tao,
        daily_usd=daily_usd_val,
        alpha_price_tao=alpha_price,
        commit_repo=champion.commit_repo,
        blocks_per_day=BLOCKS_PER_DAY,
    )
