"""Convert metagraph emission to daily miner rewards (TaoStats-compatible)."""

from __future__ import annotations

RAO_PER_TAO = 1_000_000_000
BLOCK_TIME_SECONDS = 12
BLOCKS_PER_DAY = 86_400 // BLOCK_TIME_SECONDS  # 7200 @ 12s blocks
TEMPO_BLOCKS = 360
EPOCHS_PER_DAY = BLOCKS_PER_DAY // TEMPO_BLOCKS  # 20


def rao_to_alpha(rao: float) -> float:
    return rao / RAO_PER_TAO


def normalize_emission_per_epoch(emission: float) -> float:
    """Normalize metagraph emission to α per epoch (tempo).

    - Bittensor SDK `metagraph.E` / `neuron.emission`: float α per epoch (~29.5)
    - TaoStats API `emission`: string int, RAO per epoch (~29_500_000_000)
    """
    if emission <= 0:
        return 0.0
    if emission >= 1_000_000:
        return rao_to_alpha(emission)
    return emission


def daily_alpha_from_emission_per_epoch(emission: float) -> float:
    """TaoStats: daily α ≈ epoch emission × 20 epochs/day."""
    per_epoch = normalize_emission_per_epoch(emission)
    if per_epoch <= 0:
        return 0.0
    return per_epoch * EPOCHS_PER_DAY


def daily_alpha_from_daily_reward_rao(daily_reward_rao: float) -> float:
    """TaoStats `daily_reward` field — total α per day in RAO."""
    if daily_reward_rao <= 0:
        return 0.0
    return rao_to_alpha(daily_reward_rao)


def daily_tao_equivalent(daily_alpha: float, alpha_price_tao: float | None) -> float | None:
    if daily_alpha <= 0 or alpha_price_tao is None or alpha_price_tao <= 0:
        return None
    return daily_alpha * alpha_price_tao


def daily_usd(daily_tao: float | None, tao_price_usd: float | None) -> float | None:
    if daily_tao is None or tao_price_usd is None or daily_tao <= 0:
        return None
    return daily_tao * tao_price_usd
