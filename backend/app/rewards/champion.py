"""Build champion miner daily reward summary."""

from __future__ import annotations

from app.integrations.market_client import build_market_overview
from app.integrations.taostats_client import fetch_champion_from_taostats
from app.rewards.emission_math import (
    EPOCHS_PER_DAY,
    daily_alpha_from_daily_reward_rao,
    daily_alpha_from_emission_per_epoch,
    daily_tao_equivalent,
    daily_usd,
    normalize_emission_per_epoch,
    rao_to_alpha,
)
from app.schemas.incentives import ChampionReward, MinerIncentiveEntry


def _pick_champion(miners: list[MinerIncentiveEntry]) -> MinerIncentiveEntry | None:
    if not miners:
        return None
    return max(miners, key=lambda m: (m.incentive, m.emission, -m.uid))


async def build_champion_reward(
    subnet: int,
    miners: list[MinerIncentiveEntry],
) -> ChampionReward | None:
    champion = _pick_champion(miners)
    taostats = await fetch_champion_from_taostats(subnet)

    if taostats is not None:
        daily_alpha = daily_alpha_from_daily_reward_rao(taostats.daily_reward_rao)
        if daily_alpha <= 0:
            daily_alpha = daily_alpha_from_emission_per_epoch(taostats.emission_rao_per_epoch)
        emission_epoch_alpha = rao_to_alpha(taostats.emission_rao_per_epoch)
        source = "taostats"
        uid = taostats.uid
        hotkey = taostats.hotkey
        coldkey = taostats.coldkey
        incentive = taostats.incentive
        emission_input = taostats.emission_rao_per_epoch
        daily_reward_rao = taostats.daily_reward_rao
        commit_repo = champion.commit_repo if champion and champion.uid == uid else None
    elif champion is None or (champion.incentive <= 0 and champion.emission <= 0):
        return None
    else:
        source = "metagraph"
        uid = champion.uid
        hotkey = champion.hotkey
        coldkey = champion.coldkey
        incentive = champion.incentive
        emission_input = float(champion.emission or 0.0)
        emission_epoch_alpha = normalize_emission_per_epoch(emission_input)
        daily_alpha = daily_alpha_from_emission_per_epoch(emission_input)
        daily_reward_rao = daily_alpha * 1_000_000_000
        commit_repo = champion.commit_repo

    market = await build_market_overview(subnet)
    alpha_price = market.get("alpha_price_tao")
    tao_usd = market.get("tao_price_usd")
    daily_tao = daily_tao_equivalent(daily_alpha, alpha_price)
    daily_usd_val = daily_usd(daily_tao, tao_usd)

    return ChampionReward(
        uid=uid,
        hotkey=hotkey,
        coldkey=coldkey,
        incentive=incentive,
        emission_per_epoch_alpha=emission_epoch_alpha,
        daily_alpha=daily_alpha,
        daily_tao_equivalent=daily_tao,
        daily_usd=daily_usd_val,
        alpha_price_tao=alpha_price,
        commit_repo=commit_repo,
        epochs_per_day=EPOCHS_PER_DAY,
        calculation_source=source,
        daily_reward_rao=daily_reward_rao,
        emission_raw=emission_input,
        note=(
            "TaoStats: daily_reward (RAO) from api.taostats.io when API key is set; "
            "otherwise metagraph emission × 20 epochs/day (SDK emission is α per epoch)."
        ),
    )
