"""Schemas for Albedo king status and metagraph incentives."""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field


class AlbedoKing(BaseModel):
    hotkey: str
    uid: int | None = None
    coldkey: str | None = None
    model_repo: str | None = None
    model_digest: str | None = None
    crowned_at: str | None = None
    reign_number: int | None = None
    weight: float | None = None
    weight_share: float | None = None
    registered: bool | None = None
    challenge_id: str | None = None


class AlbedoEvalStats(BaseModel):
    queued: int = 0
    accepted: int = 0
    rejected: int = 0
    failed: int = 0
    duplicates: int = 0
    injection_attempts: int = 0


class AlbedoHistoryItem(BaseModel):
    type: str
    eval_id: str | None = None
    hotkey: str | None = None
    uid: int | None = None
    model_repo: str | None = None
    accepted: bool | None = None
    winner: str | None = None
    code: str | None = None
    detail: str | None = None
    completed_at: str | None = None


class AlbedoStatusResponse(BaseModel):
    subnet: int
    updated_at: str | None = None
    source_url: str
    king: AlbedoKing | None = None
    king_chain: list[AlbedoKing] = Field(default_factory=list)
    queue_len: int = 0
    current_eval: str | None = None
    stats: AlbedoEvalStats = Field(default_factory=AlbedoEvalStats)
    recent_history: list[AlbedoHistoryItem] = Field(default_factory=list)
    dashboard_url: str = "https://us-east-1.hippius.com/albedo/index.html"


class MinerIncentiveEntry(BaseModel):
    uid: int
    hotkey: str
    coldkey: str | None = None
    incentive: float = 0.0
    emission: float = 0.0
    rank_position: int | None = None
    is_validator: bool = False
    receiving_incentive: bool = False
    is_king: bool = False
    king_model_repo: str | None = None
    commit_repo: str | None = None


class IncentiveOverviewResponse(BaseModel):
    subnet: int
    metagraph_block: int | None = None
    king: AlbedoKing | None = None
    incentivized_count: int = 0
    top_incentive: float = 0.0
    miners: list[MinerIncentiveEntry] = Field(default_factory=list)
    note: str = (
        "SN97 is winner-take-all: validators set weight 1.0 on the duel king. "
        "receiving_incentive means metagraph incentive > 0 (typically only the king)."
    )
