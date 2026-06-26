"""Convert metagraph emission (RAO per block) to daily miner rewards."""

from __future__ import annotations

RAO_PER_TAO = 1_000_000_000
BLOCK_TIME_SECONDS = 12
BLOCKS_PER_DAY = 86_400 // BLOCK_TIME_SECONDS  # 7200 @ 12s blocks
TEMPO_BLOCKS = 360
EPOCHS_PER_DAY = BLOCKS_PER_DAY // TEMPO_BLOCKS  # 20


def emission_per_block_tao(emission_rao_per_block: float) -> float:
    """Metagraph `emission` is denominated in RAO (10⁻⁹ TAO/α) per block."""
    return emission_rao_per_block / RAO_PER_TAO


def daily_alpha_from_emission_per_block(emission_rao_per_block: float) -> float:
    """Estimate daily α emissions for a neuron from per-block metagraph emission."""
    if emission_rao_per_block <= 0:
        return 0.0
    return emission_per_block_tao(emission_rao_per_block) * BLOCKS_PER_DAY


def daily_tao_equivalent(daily_alpha: float, alpha_price_tao: float | None) -> float | None:
    if daily_alpha <= 0 or alpha_price_tao is None or alpha_price_tao <= 0:
        return None
    return daily_alpha * alpha_price_tao


def daily_usd(daily_tao: float | None, tao_price_usd: float | None) -> float | None:
    if daily_tao is None or tao_price_usd is None or daily_tao <= 0:
        return None
    return daily_tao * tao_price_usd
