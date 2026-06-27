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
    sample_count: int | None = None
    generated_sample_count: int | None = None
    started_at: str | None = None


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
    hotkey: str
    uid: int
    king_model_uri: str | None = None
    king_model_name: str | None = None
    king_namespace: str | None = None
    king_uid: int | None = None
    king_hotkey: str | None = None
    king_version_defended: int | None = None
    valid_turns: int | None = None
    total_turns: int | None = None


class AlbedoKingCoronation(BaseModel):
    king_version: int
    model_uri: str
    model_name: str
    namespace: str
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
    avg_challenger_score: float
    duels: int


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
    recent_duels: list[AlbedoDuelSummary] = Field(default_factory=list)
    challenger_by_namespace: list[AlbedoWinRateRow] = Field(default_factory=list)
    challenger_by_hotkey: list[AlbedoWinRateRow] = Field(default_factory=list)
    king_defense_by_model: list[AlbedoWinRateRow] = Field(default_factory=list)
    judge_aggregates: list[AlbedoJudgeAggregate] = Field(default_factory=list)
    metric_aggregates: list[AlbedoMetricAggregate] = Field(default_factory=list)
    margin_histogram: list[AlbedoMarginBucket] = Field(default_factory=list)
    timeline: list[AlbedoTimelinePoint] = Field(default_factory=list)
    pipeline: list[AlbedoPipelineStage] = Field(default_factory=list)
    note: str = ""
