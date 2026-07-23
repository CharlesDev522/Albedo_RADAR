"""Schemas for per-duel scoring-results category / requires analysis."""

from __future__ import annotations

from pydantic import BaseModel, Field


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
    categories: list[AlbedoScoringBucketRow] = Field(default_factory=list)
    requires: list[AlbedoScoringBucketRow] = Field(default_factory=list)
    note: str = (
        "Per duel: aggregates sample×judge question answers grouped by category and requires. "
        "Requires weights: action=1.5, read=1.0, neutral=0.5. "
        "Weighted margin = weighted challenger yes-rate minus weighted king yes-rate (positive = challenger ahead)."
    )
