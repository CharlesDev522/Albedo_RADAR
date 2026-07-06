"""Tests for multi-tier registration burn alerts."""

from app.notifications.reg_fee_tiers import (
    normalize_reg_fee_thresholds,
    tiers_newly_crossed,
    tiers_to_seed_at_bootstrap,
)


def test_normalize_thresholds_from_string():
    assert normalize_reg_fee_thresholds("1, 0.75, 0.6") == [1.0, 0.75, 0.6]


def test_tiers_newly_crossed():
    thresholds = [1.0, 0.75, 0.6]
    assert tiers_newly_crossed(0.9, thresholds, set()) == [1.0]
    assert tiers_newly_crossed(0.5, thresholds, {1.0}) == [0.75, 0.6]


def test_bootstrap_seeds_all_tiers_below_burn():
    thresholds = [1.0, 0.75, 0.6]
    assert tiers_to_seed_at_bootstrap(0.5, thresholds) == {1.0, 0.75, 0.6}
