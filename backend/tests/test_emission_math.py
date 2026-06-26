"""Tests for emission → daily reward math."""

import pytest

from app.rewards.emission_math import (
    EPOCHS_PER_DAY,
    daily_alpha_from_daily_reward_rao,
    daily_alpha_from_emission_per_epoch,
    daily_tao_equivalent,
    daily_usd,
    normalize_emission_per_epoch,
)


def test_normalize_sdk_emission_is_alpha_per_epoch():
    assert normalize_emission_per_epoch(29.52) == 29.52


def test_normalize_taostats_emission_is_rao_per_epoch():
    assert normalize_emission_per_epoch(29_520_000_000) == 29.52


def test_daily_alpha_taostats_formula():
    # SDK / TaoStats convention: daily = emission_per_epoch × 20
    daily = daily_alpha_from_emission_per_epoch(29.52)
    assert daily == 29.52 * EPOCHS_PER_DAY
    assert daily == 590.4


def test_daily_alpha_from_taostats_daily_reward_rao():
    daily = daily_alpha_from_daily_reward_rao(590_400_000_000)
    assert daily == 590.4


def test_daily_tao_equivalent_and_usd():
    daily_alpha = 590.4
    alpha_price = 0.0347
    tao = daily_tao_equivalent(daily_alpha, alpha_price)
    assert tao == pytest.approx(20.48688)
    usd = daily_usd(tao, 200.0)
    assert usd == pytest.approx(4097.376)
