"""Tests for champion reward builder."""

from unittest.mock import AsyncMock, patch

import pytest

from app.rewards.champion import build_champion_reward
from app.schemas.incentives import MinerIncentiveEntry


@pytest.mark.asyncio
async def test_build_champion_reward_metagraph_formula():
    miners = [
        MinerIncentiveEntry(uid=1, hotkey="a", incentive=0.1, emission=10.0),
        MinerIncentiveEntry(uid=2, hotkey="b", incentive=0.9, emission=29.52),
    ]
    with patch(
        "app.rewards.champion.fetch_champion_from_taostats",
        new_callable=AsyncMock,
        return_value=None,
    ), patch(
        "app.rewards.champion.build_market_overview",
        new_callable=AsyncMock,
        return_value={"alpha_price_tao": 0.0347, "tao_price_usd": 200.0},
    ):
        champion = await build_champion_reward(97, miners)

    assert champion is not None
    assert champion.uid == 2
    assert champion.calculation_source == "metagraph"
    assert champion.emission_per_epoch_alpha == pytest.approx(29.52)
    assert champion.daily_alpha == pytest.approx(590.4)
    assert champion.daily_tao_equivalent == pytest.approx(590.4 * 0.0347)


@pytest.mark.asyncio
async def test_build_champion_reward_prefers_taostats_daily_reward():
    from app.integrations.taostats_client import TaoStatsChampion

    miners = [MinerIncentiveEntry(uid=49, hotkey="hk", incentive=0.2, emission=29.52)]
    ts = TaoStatsChampion(
        uid=49,
        hotkey="hk",
        coldkey=None,
        incentive=0.199985,
        emission_rao_per_epoch=29_520_000_000,
        daily_reward_rao=590_400_000_000,
        block_number=1,
        timestamp="2026-01-01T00:00:00Z",
    )
    with patch(
        "app.rewards.champion.fetch_champion_from_taostats",
        new_callable=AsyncMock,
        return_value=ts,
    ), patch(
        "app.rewards.champion.build_market_overview",
        new_callable=AsyncMock,
        return_value={"alpha_price_tao": 0.0347, "tao_price_usd": 200.0},
    ):
        champion = await build_champion_reward(97, miners)

    assert champion is not None
    assert champion.calculation_source == "taostats"
    assert champion.daily_alpha == pytest.approx(590.4)
