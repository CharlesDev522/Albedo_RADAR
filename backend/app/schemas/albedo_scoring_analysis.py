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
    bucket_contribution: str = (
        "Per bucket: contribution = (bucket_weight / total_weight) × bucket_partial_rate. "
        "Requires contributions sum to the base score before the size multiplier."
    )
    bucket_partial_rate: str = "Weighted yes-rate within the bucket only (non-size questions)."
    bucket_share: str = "Share of absolute margin between buckets (diagnostic)."


class AlbedoScoringOverallSummary(BaseModel):
    observation_count: int = 0
    weighted_challenger_score_pct: float = 0.0
    weighted_king_score_pct: float = 0.0
    weighted_margin_pct: float = 0.0
    dashboard_score_challenger: float | None = None
    dashboard_score_king: float | None = None
    dashboard_win_margin: float | None = None
    replicated_valid_samples: int = 0
    base_challenger_score_pct: float | None = None
    base_king_score_pct: float | None = None
    requires_contrib_challenger_pct: float | None = None
    requires_contrib_king_pct: float | None = None
    challenger_win_margin: float = 0.03
    jsonl_matches_dashboard: bool = False
    requires_contrib_matches_base: bool = False


class AlbedoScoringBucketRow(BaseModel):
    key: str
    weight_multiplier: float | None = None
    question_slots: int = 0
    weight_share_pct: float = 0.0
    challenger_yes_rate: float = 0.0
    king_yes_rate: float = 0.0
    weighted_challenger_score: float = 0.0
    weighted_king_score: float = 0.0
    weighted_margin: float = 0.0
    share_of_abs_weighted_margin_pct: float = 0.0
    note: str | None = None


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
        "Requires rows show additive contributions to the base score (before size multiplier). "
        "_base sums requires contributions; _final is the duel score from dashboard.json."
    )
