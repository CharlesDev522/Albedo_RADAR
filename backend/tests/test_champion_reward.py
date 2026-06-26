"""Tests for champion reward builder."""

from unittest.mock import AsyncMock, patch

import pytest

from app.rewards.champion import build_champion_reward
from app.schemas.incentives import MinerIncentiveEntry


@pytest.mark.asyncio
async def test_build_champion_reward_picks_top_incentive():
    miners = [
        MinerIncentiveEntry(uid=1, hotkey="a", incentive=0.1, emission=1_000_000),
        MinerIncentiveEntry(uid=2, hotkey="b", incentive=0.9, emission=2_000_000),
    ]
    with patch(
        "app.rewards.champion.build_market_overview",
        new_callable=AsyncMock,
        return_value={"alpha_price_tao": 0.1, "tao_price_usd": 100.0},
    ):
        champion = await build_champion_reward(97, miners)

    assert champion is not None
    assert champion.uid == 2
    assert champion.incentive == 0.9
    assert champion.daily_alpha == pytest.approx(0.002 * 7200)
    assert champion.daily_tao_equivalent == pytest.approx(champion.daily_alpha * 0.1)
