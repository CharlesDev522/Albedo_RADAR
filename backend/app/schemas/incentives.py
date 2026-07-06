"""Metagraph incentive overview (subnet-agnostic, no king linkage)."""

from __future__ import annotations

from pydantic import BaseModel, Field


class MinerIncentiveEntry(BaseModel):
    uid: int
    hotkey: str
    coldkey: str | None = None
    incentive: float = 0.0
    emission: float = 0.0
    rank_position: int | None = None
    is_validator: bool = False
    receiving_incentive: bool = False
    commit_repo: str | None = None


class ChampionReward(BaseModel):
    """Daily reward estimate for the current subnet champion (top incentive miner)."""

    uid: int | None = None
    hotkey: str | None = None
    coldkey: str | None = None
    incentive: float = 0.0
    emission_per_epoch_alpha: float = 0.0
    daily_alpha: float = 0.0
    daily_tao_equivalent: float | None = None
    daily_usd: float | None = None
    alpha_price_tao: float | None = None
    commit_repo: str | None = None
    epochs_per_day: int = 20
    calculation_source: str = "metagraph"
    daily_reward_rao: float | None = None
    emission_raw: float | None = None
    note: str = (
        "Daily α from TaoStats daily_reward when available, else metagraph emission × 20 epochs/day. "
        "Bittensor SDK emission is α granted per tempo (~360 blocks), not RAO per block."
    )


class IncentiveOverviewResponse(BaseModel):
    subnet: int
    metagraph_block: int | None = None
    incentivized_count: int = 0
    top_incentive: float = 0.0
    miners: list[MinerIncentiveEntry] = Field(default_factory=list)
    champion: ChampionReward | None = None
    note: str = (
        "receiving_incentive means metagraph incentive > 0. "
        "Winner-take-all subnets typically show incentive on one miner."
    )
