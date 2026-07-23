"""Schemas for per-duel scoring-results category / requires analysis."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AlbedoScoringFormula(BaseModel):
    requires_weights: dict[str, float] = Field(
        default_factory=lambda: {"action": 1.5, "read": 1.0, "neutral": 0.5}
    )
    side_score: str = "sum(answer × requires_weight) / sum(requires_weight) per sample×judge"
    observation_margin: str = "challenger_side_score − king_side_score (range −1..+1)"
    bucket_weighted_margin: str = (
        "(Σ challenger×weight − Σ king×weight) / Σ weight across question slots in bucket"
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
    formula: AlbedoScoringFormula = Field(default_factory=AlbedoScoringFormula)
    overall: AlbedoScoringOverallSummary = Field(default_factory=AlbedoScoringOverallSummary)
    categories: list[AlbedoScoringBucketRow] = Field(default_factory=list)
    requires: list[AlbedoScoringBucketRow] = Field(default_factory=list)
    note: str = (
        "Overall scores average per sample×judge weighted side scores. "
        "Category/requires tables pool question slots with each question weighted by its requires field."
    )
