"""Schemas for per-sample challenger vs king score gap analysis."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SampleGapBucket = Literal["close", "moderate", "decisive"]
ScoreCaseCategory = Literal["gap_band", "loser_band", "edge"]


class GapBucketCounts(BaseModel):
    close: int = 0
    moderate: int = 0
    decisive: int = 0
    total: int = 0


class GapBucketDistribution(BaseModel):
    counts: GapBucketCounts = Field(default_factory=GapBucketCounts)
    close_pct: float = 0.0
    moderate_pct: float = 0.0
    decisive_pct: float = 0.0


class ScoreCaseRow(BaseModel):
    case_id: str
    label: str
    category: ScoreCaseCategory = "edge"
    observations: int = 0
    observations_pct: float = 0.0
    total_gap_points: float = 0.0
    gap_share_pct: float = 0.0
    avg_gap: float = 0.0
    avg_lower_score: float = 0.0
    avg_higher_score: float = 0.0


class JudgeMarginShare(BaseModel):
    judge_model: str
    short_name: str
    observations: int = 0
    total_gap_points: float = 0.0
    gap_share_pct: float = 0.0
    avg_gap: float = 0.0
    pick_challenger_pct: float = 0.0


class JudgeSampleGapSummary(BaseModel):
    judge_model: str
    short_name: str
    observations: int = 0
    distribution: GapBucketDistribution = Field(default_factory=GapBucketDistribution)
    avg_challenger_pct: float = 0.0
    avg_king_pct: float = 0.0
    avg_gap_pct: float = 0.0
    pick_challenger_pct: float = 0.0
    total_gap_points: float = 0.0
    gap_share_pct: float = 0.0


class JudgePairAgreement(BaseModel):
    judge_a: str
    judge_b: str
    short_name_a: str
    short_name_b: str
    observations: int = 0
    same_bucket_pct: float = 0.0
    same_pick_pct: float = 0.0
    avg_score_delta_pct: float = 0.0


class DuelSampleGapSummary(BaseModel):
    eval_run_id: str
    finished_at: str = ""
    challenger_label: str = ""
    king_label: str = ""
    winner: str = ""
    sample_count: int = 0
    judge_count: int = 0
    observations: int = 0
    total_gap_points: float = 0.0
    distribution: GapBucketDistribution = Field(default_factory=GapBucketDistribution)
    gap_bands: list[ScoreCaseRow] = Field(default_factory=list)
    edge_cases: list[ScoreCaseRow] = Field(default_factory=list)
    judge_margin_shares: list[JudgeMarginShare] = Field(default_factory=list)
    judges: list[JudgeSampleGapSummary] = Field(default_factory=list)


class AlbedoSampleScoreAnalysis(BaseModel):
    binary_duels_total: int = 0
    binary_duels_scanned: int = 0
    binary_duels_with_samples: int = 0
    total_samples: int = 0
    total_observations: int = 0
    total_gap_points: float = 0.0
    judge_models: list[str] = Field(default_factory=list)
    overall: GapBucketDistribution = Field(default_factory=GapBucketDistribution)
    gap_bands: list[ScoreCaseRow] = Field(default_factory=list)
    loser_bands: list[ScoreCaseRow] = Field(default_factory=list)
    edge_cases: list[ScoreCaseRow] = Field(default_factory=list)
    judge_margin_shares: list[JudgeMarginShare] = Field(default_factory=list)
    by_judge: list[JudgeSampleGapSummary] = Field(default_factory=list)
    judge_pairs: list[JudgePairAgreement] = Field(default_factory=list)
    duels: list[DuelSampleGapSummary] = Field(default_factory=list)
    updated_at: str | None = None
