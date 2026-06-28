"""Schemas for Albedo duel / king-of-the-hill analysis."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AlbedoReignMember(BaseModel):
    king_version: int
    model_uri: str
    model_name: str
    namespace: str
    hotkey: str
    uid: int
    weight_bps: int
    repo: str | None = None
    coldkey: str | None = None
    score_challenger: float | None = None
    score_king: float | None = None
    eval_run_id: str | None = None


class AlbedoCurrentEval(BaseModel):
    eval_run_id: str
    state: str
    model_uri: str
    model_name: str
    namespace: str
    hotkey: str
    uid: int
    repo: str | None = None
    coldkey: str | None = None
    sample_count: int | None = None
    generated_sample_count: int | None = None
    started_at: str | None = None


class AlbedoDuelJudgeVote(BaseModel):
    judge: str
    short_name: str
    challenger_score: float
    king_score: float
    pick_challenger: bool
    agrees_with_verdict: bool
    margin_from_neutral: float


class AlbedoDuelSummary(BaseModel):
    eval_run_id: str
    finished_at: str
    challenger_won: bool
    coronated: bool
    king_version: int | None = None
    score_challenger: float
    score_king: float
    win_margin: float
    model_uri: str
    model_name: str
    namespace: str
    repo: str | None = None
    coldkey: str | None = None
    hotkey: str
    uid: int
    king_model_uri: str | None = None
    king_model_name: str | None = None
    king_namespace: str | None = None
    king_repo: str | None = None
    king_coldkey: str | None = None
    king_uid: int | None = None
    king_hotkey: str | None = None
    king_version_defended: int | None = None
    valid_turns: int | None = None
    total_turns: int | None = None
    judge_scores: dict[str, float] = Field(default_factory=dict)
    judge_votes: list[AlbedoDuelJudgeVote] = Field(default_factory=list)
    judge_spread: float | None = None
    panel_pattern: str | None = None
    unanimous_panel: bool = False


class AlbedoKingCoronation(BaseModel):
    king_version: int
    model_uri: str
    model_name: str
    namespace: str
    repo: str | None = None
    coldkey: str | None = None
    hotkey: str
    uid: int
    finished_at: str
    eval_run_id: str
    score_challenger: float
    score_king: float
    win_margin: float
    defeated_king_version: int | None = None
    defeated_model_uri: str | None = None
    defeated_model_name: str | None = None
    defeated_namespace: str | None = None
    defeated_repo: str | None = None
    defeated_coldkey: str | None = None


class AlbedoWinRateRow(BaseModel):
    key: str
    label: str
    duels: int
    wins: int
    losses: int
    win_pct: float
    avg_margin: float | None = None
    coronations: int = 0


class AlbedoJudgeAggregate(BaseModel):
    judge: str
    short_name: str
    avg_challenger_score: float
    duels: int


class AlbedoJudgeDetail(BaseModel):
    judge: str
    short_name: str
    duels: int
    avg_challenger_score: float
    avg_king_score: float
    score_std: float | None = None
    pick_challenger_pct: float
    pick_king_pct: float
    agree_verdict_pct: float
    overturn_duels: int
    split_majority_align_pct: float | None = None
    solo_dissent_win_pct: float | None = None
    extreme_call_pct: float | None = None
    avg_score_when_challenger_wins: float | None = None
    avg_score_when_king_wins: float | None = None
    unanimous_challenger_duels: int = 0
    unanimous_king_duels: int = 0
    split_duels: int = 0


class AlbedoJudgeConsensus(BaseModel):
    pattern: str
    label: str
    duels: int
    pct: float
    challenger_wins: int
    king_wins: int


class AlbedoMetricAggregate(BaseModel):
    metric: str
    avg_challenger_score: float
    duels: int


class AlbedoMarginBucket(BaseModel):
    label: str
    count: int


class AlbedoTimelinePoint(BaseModel):
    date: str
    duels: int
    challenger_wins: int
    king_wins: int
    coronations: int
    challenger_win_pct: float


class AlbedoPipelineStage(BaseModel):
    stage: str
    status: str | None = None
    detail: str | None = None


class AlbedoReignSlotHolder(BaseModel):
    key: str
    label: str
    repo: str | None = None
    coldkey: str | None = None
    hotkey: str
    uid: int
    slots_held: int
    weight_bps: int
    weight_pct: float
    king_versions: list[int] = Field(default_factory=list)


class AlbedoKingTenure(BaseModel):
    king_version: int
    model_uri: str
    model_name: str
    namespace: str
    repo: str | None = None
    coldkey: str | None = None
    hotkey: str
    uid: int
    reign_rank: int | None = None
    weight_bps: int = 0
    weight_pct: float = 0.0
    reign_slots: int = 1
    is_current_king: bool = False
    in_reign_chain: bool = True
    coronation_at: str | None = None
    active_until: str | None = None
    slot_until: str | None = None
    active_tenure_hours: float | None = None
    slot_tenure_hours: float | None = None
    defenses: int = 0
    attacks_faced: int = 0
    defense_pct: float | None = None
    coronation_margin: float | None = None
    defeated_king_version: int | None = None


class AlbedoCrownEvent(BaseModel):
    king_version: int
    crowned_at: str
    active_until: str | None = None
    slot_until: str | None = None
    active_hours: float | None = None
    slot_hours: float | None = None
    weight_bps: int = 0
    estimated_alpha: float | None = None
    estimated_tao: float | None = None
    repo: str | None = None
    coldkey: str | None = None
    hotkey: str
    uid: int
    model_name: str
    is_current_king: bool = False


class AlbedoRewardBasis(BaseModel):
    daily_subnet_alpha: float = 0.0
    alpha_price_tao: float | None = None
    tao_price_usd: float | None = None
    daily_subnet_tao: float | None = None
    daily_subnet_usd: float | None = None
    calculation_source: str = "unavailable"
    default_weight_bps: int = 2000
    note: str = ""


class AlbedoCrownLeaderboardRow(BaseModel):
    key: str
    label: str
    group_type: str
    coronations: int
    total_active_hours: float
    total_slot_hours: float
    current_weight_pct: float
    reign_slots: int
    owner_count: int = 0
    multi_owner: bool = False
    coldkeys: list[str] = Field(default_factory=list)
    hotkeys: list[str] = Field(default_factory=list)
    uids: list[int] = Field(default_factory=list)
    duel_count: int = 0
    challenger_wins: int = 0
    challenger_win_pct: float | None = None
    total_estimated_alpha: float | None = None
    total_estimated_tao: float | None = None
    ongoing_daily_alpha: float | None = None
    crown_events: list[AlbedoCrownEvent] = Field(default_factory=list)


class AlbedoRepoColdkeyLink(BaseModel):
    repo: str
    coldkey: str
    hotkey: str | None = None
    uid: int | None = None
    coronations: int = 0
    total_slot_hours: float = 0.0
    total_active_hours: float = 0.0
    total_estimated_alpha: float | None = None
    total_estimated_tao: float | None = None
    ongoing_daily_alpha: float | None = None
    in_reign: bool = False
    last_crowned_at: str | None = None


class AlbedoRepoCrownAnalysis(BaseModel):
    reward_basis: AlbedoRewardBasis = Field(default_factory=AlbedoRewardBasis)
    crowns_by_repo: list[AlbedoCrownLeaderboardRow] = Field(default_factory=list)
    crowns_by_coldkey: list[AlbedoCrownLeaderboardRow] = Field(default_factory=list)
    repo_coldkey_links: list[AlbedoRepoColdkeyLink] = Field(default_factory=list)
    multi_owner_repos: list[str] = Field(default_factory=list)
    total_repos_crowned: int = 0
    total_unique_coldkeys: int = 0
    grand_total_estimated_alpha: float | None = None
    grand_total_estimated_tao: float | None = None


class AlbedoAnalysisOverview(BaseModel):
    subnet: int = 97
    source: str = "hippius_dashboard"
    source_url: str
    updated_at: str | None = None
    judge_models: list[str] = Field(default_factory=list)
    total_duels: int = 0
    challenger_wins: int = 0
    king_wins: int = 0
    coronations: int = 0
    challenger_win_pct: float = 0.0
    king_win_pct: float = 0.0
    avg_win_margin: float | None = None
    avg_challenger_score: float | None = None
    avg_king_score: float | None = None
    reign: list[AlbedoReignMember] = Field(default_factory=list)
    current_king: AlbedoReignMember | None = None
    current_eval: AlbedoCurrentEval | None = None
    queue_length: int = 0
    king_history: list[AlbedoKingCoronation] = Field(default_factory=list)
    king_tenures: list[AlbedoKingTenure] = Field(default_factory=list)
    reign_slot_holders: list[AlbedoReignSlotHolder] = Field(default_factory=list)
    repo_crown_analysis: AlbedoRepoCrownAnalysis = Field(default_factory=AlbedoRepoCrownAnalysis)
    crowns_by_repo: list[AlbedoCrownLeaderboardRow] = Field(default_factory=list)
    crowns_by_coldkey: list[AlbedoCrownLeaderboardRow] = Field(default_factory=list)
    recent_duels: list[AlbedoDuelSummary] = Field(default_factory=list)
    challenger_by_namespace: list[AlbedoWinRateRow] = Field(default_factory=list)
    challenger_by_hotkey: list[AlbedoWinRateRow] = Field(default_factory=list)
    challenger_by_repo: list[AlbedoWinRateRow] = Field(default_factory=list)
    king_defense_by_model: list[AlbedoWinRateRow] = Field(default_factory=list)
    judge_aggregates: list[AlbedoJudgeAggregate] = Field(default_factory=list)
    judge_details: list[AlbedoJudgeDetail] = Field(default_factory=list)
    judge_consensus: list[AlbedoJudgeConsensus] = Field(default_factory=list)
    metric_aggregates: list[AlbedoMetricAggregate] = Field(default_factory=list)
    margin_histogram: list[AlbedoMarginBucket] = Field(default_factory=list)
    timeline: list[AlbedoTimelinePoint] = Field(default_factory=list)
    pipeline: list[AlbedoPipelineStage] = Field(default_factory=list)
    miner_lookup_coverage_pct: float | None = None
    note: str = ""
