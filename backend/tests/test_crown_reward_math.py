"""Tests for crown reward estimation."""

from app.rewards.crown_reward_math import (
    DEFAULT_KING_WEIGHT_BPS,
    estimate_crown_alpha,
    hourly_subnet_alpha,
    ongoing_daily_alpha,
    weight_share,
)


def test_weight_share_and_hourly():
    assert weight_share(2000) == 0.2
    assert hourly_subnet_alpha(240.0) == 10.0


def test_estimate_crown_alpha_one_day_at_twenty_percent():
    # 24h at 20% of 100 α/day subnet => 20 α
    alpha = estimate_crown_alpha(
        24.0,
        weight_bps=DEFAULT_KING_WEIGHT_BPS,
        daily_subnet_alpha=100.0,
    )
    assert alpha == 20.0


def test_ongoing_daily_alpha():
    daily = ongoing_daily_alpha(weight_bps=2000, daily_subnet_alpha=500.0)
    assert daily == 100.0
