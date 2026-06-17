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


class IncentiveOverviewResponse(BaseModel):
    subnet: int
    metagraph_block: int | None = None
    incentivized_count: int = 0
    top_incentive: float = 0.0
    miners: list[MinerIncentiveEntry] = Field(default_factory=list)
    note: str = (
        "receiving_incentive means metagraph incentive > 0. "
        "Winner-take-all subnets typically show incentive on one miner."
    )
