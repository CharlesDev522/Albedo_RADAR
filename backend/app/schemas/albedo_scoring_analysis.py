"""Schemas for per-duel scoring-results category / requires analysis."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AlbedoScoringFormula(BaseModel):
    requires_weights: dict[str, float] = Field(
        default_factory=lambda: {"action": 2.0, "read": 0.75, "neutral": 0.25}
    )
    size_factor_floor: float = 0.6
    challenger_win_margin: float = 0.03
    side_score: str = (
        "Per judge: weighted mean of 1/0 answers using requires weights; "
        "size-category questions excluded from the mean and applied as a multiplier "
        "(floor + (1-floor)×size_yes_rate)."
    )
    duel_score: str = "Mean of per-sample side scores across scored samples (matches dashboard.json)."
    observation_margin: str = "challenger_side_score − king_side_score per sample (0..1 scale)."
    bucket_weighted_margin: str = (
        "Non-size question slots only: (Σ challenger×weight − Σ king×weight) / Σ weight"
    )
    bucket_share: str = "Σ|challenger−king|×weight in bucket / Σ|challenger−king|×weight overall"


class AlbedoScoringOverallSummary(BaseModel):
    observation_count: int = 0
    weighted_challenger_score_pct: float = 0.0
    weighted_king_score_pct: float = 0.0
    weighted_margin_pct: float = 0.0
    dashboard_score_challenger: float | None = None
    dashboard_score_king: float | None = None
    dashboard_win_margin: float | None = None
    replicated_valid_samples: int = 0
    challenger_win_margin: float = 0.03
    jsonl_matches_dashboard: bool = False


class AlbedoScoringBucketRow(BaseModel):
    key: str
    weight_multiplier: float | None = None
    question_slots: int = 0
    challenger_yes_rate: float = 0.0
    king_yes_rate: float = 0.0
    weighted_challenger_score: float = 0.0
    weighted_king_score: float = 0.0
    weighted_margin: float = 0.0
    share_of_abs_weighted_margin_pct: float = 0.0


class AlbedoScoringDuelAnalysis(BaseModel):
    eval_run_id: str
    finished_at: str | None = None
    challenger_label: str
    king_label: str | None = None
    challenger_won: bool = False
    coronated: bool = False
    total_samples: int = 0
    judge_observations: int = 0
    question_slots: int = 0
    size_question_slots: int = 0
    formula: AlbedoScoringFormula = Field(default_factory=AlbedoScoringFormula)
    overall: AlbedoScoringOverallSummary = Field(default_factory=AlbedoScoringOverallSummary)
    categories: list[AlbedoScoringBucketRow] = Field(default_factory=list)
    requires: list[AlbedoScoringBucketRow] = Field(default_factory=list)
    note: str = (
        "Replicated scores use the Albedo validator rubric (action=2.0, read=0.75, neutral=0.25, "
        "size multiplier). Dashboard scores should match when the full scoring-results artifact is present."
    )
