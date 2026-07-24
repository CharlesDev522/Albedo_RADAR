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
    scoring_mode: str | None = None
    required_win_margin: float | None = None
    margin_cleared: bool | None = None
    scored_sample_count: int | None = None
    judge_errors: int | None = None
    metric_breakdown: dict[str, float] = Field(default_factory=dict)
    category_breakdown: dict[str, float] = Field(default_factory=dict)
    artifacts: dict[str, str] = Field(default_factory=dict)
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


class AlbedoScoreTimelinePoint(BaseModel):
    """One finished duel on the rolling score timeline (typically last 24h)."""

    eval_run_id: str
    finished_at: str
    score_challenger: float
    score_king: float
    win_margin: float
    challenger_won: bool
    coronated: bool
    challenger_uid: int
    king_uid: int | None = None
    challenger_label: str = ""
    king_label: str = ""


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
    voided_bridge_hours: float | None = None
    defenses: int = 0
    attacks_faced: int = 0
    defense_pct: float | None = None
    coronation_margin: float | None = None
    defeated_king_version: int | None = None


class AlbedoAnalysisOverview(BaseModel):
    subnet: int = 97
    source: str = "albedo_dashboard"
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
    required_win_margin: float | None = None
    binary_scoring_duels: int = 0
    reign: list[AlbedoReignMember] = Field(default_factory=list)
    current_king: AlbedoReignMember | None = None
    current_eval: AlbedoCurrentEval | None = None
    queue_length: int = 0
    king_history: list[AlbedoKingCoronation] = Field(default_factory=list)
    king_tenures: list[AlbedoKingTenure] = Field(default_factory=list)
    reign_slot_holders: list[AlbedoReignSlotHolder] = Field(default_factory=list)
    voided_king_versions: list[int] = Field(default_factory=list)
    crown_history_coverage_note: str = ""
    recent_duels: list[AlbedoDuelSummary] = Field(default_factory=list)
    challenger_by_namespace: list[AlbedoWinRateRow] = Field(default_factory=list)
    challenger_by_hotkey: list[AlbedoWinRateRow] = Field(default_factory=list)
    challenger_by_repo: list[AlbedoWinRateRow] = Field(default_factory=list)
    king_defense_by_model: list[AlbedoWinRateRow] = Field(default_factory=list)
    margin_histogram: list[AlbedoMarginBucket] = Field(default_factory=list)
    timeline: list[AlbedoTimelinePoint] = Field(default_factory=list)
    score_timeline: list[AlbedoScoreTimelinePoint] = Field(default_factory=list)
    pipeline: list[AlbedoPipelineStage] = Field(default_factory=list)
    miner_lookup_coverage_pct: float | None = None
    note: str = ""
