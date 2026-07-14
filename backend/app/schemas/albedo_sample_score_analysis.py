"""Schemas for per-sample challenger vs king score gap analysis."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

SampleGapBucket = Literal["close", "moderate", "decisive"]

GAP_TYPE_LABELS: dict[SampleGapBucket, str] = {
    "close": "Close (gap ≤20%)",
    "moderate": "Moderate (20–50% gap)",
    "decisive": "Decisive (gap >50% & leader >90%)",
}

GAP_TYPE_CRITERIA: dict[SampleGapBucket, str] = {
    "close": "Score difference ≤ 20 percentage points",
    "moderate": "Gap > 20 and not decisive (includes wide low-confidence)",
    "decisive": "Gap > 50 and higher side > 90%",
}


class GapDiffBin(BaseModel):
    """Score-difference bin. share_pct = % of total margin mass (all slices sum to 100)."""

    label: str
    bin_min: float
    bin_max: float
    share_pct: float = 0.0


class GapTypeSummary(BaseModel):
    gap_type: SampleGapBucket
    label: str
    criteria: str
    share_pct: float = 0.0
    avg_margin_pct: float = 0.0
    gap_distribution: list[GapDiffBin] = Field(default_factory=list)


class JudgeMarginShare(BaseModel):
    judge_model: str
    short_name: str
    observations: int = 0
    share_pct: float = 0.0
    avg_margin_pct: float = 0.0
    pick_challenger_pct: float = 0.0
    by_gap_type: list[GapTypeSummary] = Field(default_factory=list)


class JudgeSampleGapSummary(BaseModel):
    judge_model: str
    short_name: str
    observations: int = 0
    avg_challenger_pct: float = 0.0
    avg_king_pct: float = 0.0
    avg_margin_pct: float = 0.0
    pick_challenger_pct: float = 0.0
    share_pct: float = 0.0


class JudgePairAgreement(BaseModel):
    judge_a: str
    judge_b: str
    short_name_a: str
    short_name_b: str
    observations: int = 0
    same_type_pct: float = 0.0
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
    gap_types: list[GapTypeSummary] = Field(default_factory=list)
    judge_margin_shares: list[JudgeMarginShare] = Field(default_factory=list)
    judges: list[JudgeSampleGapSummary] = Field(default_factory=list)


class AlbedoSampleScoreAnalysis(BaseModel):
    binary_duels_total: int = 0
    binary_duels_scanned: int = 0
    binary_duels_with_samples: int = 0
    total_samples: int = 0
    total_observations: int = 0
    judge_models: list[str] = Field(default_factory=list)
    gap_types: list[GapTypeSummary] = Field(default_factory=list)
    judge_margin_shares: list[JudgeMarginShare] = Field(default_factory=list)
    by_judge: list[JudgeSampleGapSummary] = Field(default_factory=list)
    judge_pairs: list[JudgePairAgreement] = Field(default_factory=list)
    duels: list[DuelSampleGapSummary] = Field(default_factory=list)
    updated_at: str | None = None
