"""Tests for emission → daily reward math."""

from app.rewards.emission_math import (
    BLOCKS_PER_DAY,
    daily_alpha_from_emission_per_block,
    daily_tao_equivalent,
    daily_usd,
    emission_per_block_tao,
)


def test_emission_per_block_tao():
    assert emission_per_block_tao(1_000_000_000) == 1.0
    assert emission_per_block_tao(500_000_000) == 0.5


def test_daily_alpha_from_emission():
    # 1M RAO/block → 0.001 α/block → 7.2 α/day @ 7200 blocks
    daily = daily_alpha_from_emission_per_block(1_000_000)
    assert daily == 0.001 * BLOCKS_PER_DAY
    assert daily == 7.2


def test_daily_tao_equivalent_and_usd():
    daily_alpha = 10.0
    alpha_price = 0.05
    tao = daily_tao_equivalent(daily_alpha, alpha_price)
    assert tao == 0.5
    usd = daily_usd(tao, 200.0)
    assert usd == 100.0
