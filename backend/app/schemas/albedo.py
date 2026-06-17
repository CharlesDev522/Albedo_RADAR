"""Schemas for Albedo v2 dashboard, duels, and HF-account analytics."""

from __future__ import annotations

from pydantic import BaseModel, Field


class ReignMember(BaseModel):
    king_version: int | None = None
    title: str | None = None
    uid: int | None = None
    hotkey: str | None = None
    coldkey: str | None = None
    model_uri: str | None = None
    model_repo: str | None = None
    hf_account: str | None = None
    weight_bps: int | None = None
    weight_pct: float | None = None
    score_challenger: float | None = None
    score_king: float | None = None


class PipelineCounts(BaseModel):
    running: int = 0
    queued: int = 0


class AlbedoPipelineState(BaseModel):
    updated_at: str | None = None
    validate: PipelineCounts = Field(default_factory=PipelineCounts)
    pre_eval: PipelineCounts = Field(default_factory=PipelineCounts)
    eval: PipelineCounts = Field(default_factory=PipelineCounts)
    total_in_flight: int = 0


class DuelRun(BaseModel):
    eval_run_id: str | None = None
    uid: int | None = None
    hotkey: str | None = None
    model_uri: str | None = None
    model_repo: str | None = None
    hf_account: str | None = None
    king_version: int | None = None
    challenger_won: bool = False
    coronated: bool = False
    badge: str = "lost"
    score_challenger: float | None = None
    score_king: float | None = None
    win_margin: float | None = None
    finished_at: str | None = None
    defeated_king_hf: str | None = None


class FailRun(BaseModel):
    eval_run_id: str | None = None
    uid: int | None = None
    hotkey: str | None = None
    model_uri: str | None = None
    hf_account: str | None = None
    fault_code: str | None = None
    fault_class: str | None = None
    finished_at: str | None = None


class HfAccountStats(BaseModel):
    hf_account: str
    coldkeys: list[str] = Field(default_factory=list)
    hotkey_count: int = 0
    challenges: int = 0
    duel_wins: int = 0
    duel_losses: int = 0
    crowns: int = 0
    dethrones_caused: int = 0
    times_dethroned: int = 0
    reign_versions: list[int] = Field(default_factory=list)
    win_rate: float = 0.0
    crown_rate: float = 0.0
    dethrone_rate: float = 0.0
    avg_win_margin: float | None = None


class HfAnalyticsSummary(BaseModel):
    total_eval_runs: int = 0
    total_crownings: int = 0
    unique_hf_accounts: int = 0
    top_crown_holder: str | None = None
    crown_share_top: float = 0.0


class HfAnalyticsResponse(BaseModel):
    subnet: int
    updated_at: str | None = None
    summary: HfAnalyticsSummary
    accounts: list[HfAccountStats] = Field(default_factory=list)


class AlbedoStatusResponse(BaseModel):
    subnet: int
    updated_at: str | None = None
    schema_version: int = 2
    source_url: str
    dashboard_url: str = "https://us-east-1.hippius.com/albedo/index.html"
    current_king: ReignMember | None = None
    reign_chain: list[ReignMember] = Field(default_factory=list)
    crownings: list[DuelRun] = Field(default_factory=list)
    recent_duels: list[DuelRun] = Field(default_factory=list)
    recent_fails: list[FailRun] = Field(default_factory=list)
    pipeline: AlbedoPipelineState | None = None
    stats: dict = Field(default_factory=dict)
    queue_len: int = 0
    current_eval: str | None = None


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
    king: ReignMember | None = None
    incentivized_count: int = 0
    top_incentive: float = 0.0
    miners: list[MinerIncentiveEntry] = Field(default_factory=list)
    note: str = (
        "SN97 is winner-take-all: validators set weight 1.0 on the duel king. "
        "receiving_incentive means metagraph incentive > 0 (typically only the king)."
    )
