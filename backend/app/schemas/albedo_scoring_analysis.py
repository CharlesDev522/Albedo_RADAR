"""Schemas for Albedo scoring-results.jsonl GLM+Qwen consensus question analysis."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field

ScoringConsensusPolarity = Literal["zero", "one"]


class AlbedoDualZeroQuestion(BaseModel):
    question_id: str
    text: str
    example_bad: str | None = None
    challenger_glm: str | None = None
    challenger_qwen: str | None = None
    king_glm: str | None = None
    king_qwen: str | None = None


class AlbedoSampleDualZeros(BaseModel):
    sample_id: str
    dual_zero_count: int = 0
    questions: list[AlbedoDualZeroQuestion] = Field(default_factory=list)


class AlbedoScoringAnalysis(BaseModel):
    polarity: ScoringConsensusPolarity = "zero"
    export_filename: str | None = None
    total_samples: int = 0
    samples_with_dual_zeros: int = 0
    total_dual_zero_questions: int = 0
    samples: list[AlbedoSampleDualZeros] = Field(default_factory=list)


class KingReignDatasetSlice(BaseModel):
    king_version: int
    coronation_at: str = ""
    active_until: str | None = None
    binary_duels_scanned: int = 0
    binary_duels_with_dual_zero: int = 0


class AlbedoDatasetBuildSummary(BaseModel):
    polarity: ScoringConsensusPolarity = "zero"
    export_filename: str = "binary-dual-zero-dataset.jsonl"
    dedup_script_filename: str = "dedup_dual_zero_jsonl.py"
    build_mode: Literal["recent", "king_reign"] = "recent"
    king_versions: list[int] = Field(default_factory=list)
    king_reign_breakdown: list[KingReignDatasetSlice] = Field(default_factory=list)
    min_questions_per_sample: int = 6
    recent_duels_limit: int = 20
    binary_duels_total: int = 0
    binary_duels_with_scoring: int = 0
    binary_duels_scanned: int = 0
    binary_duels_with_dual_zero: int = 0
    samples_before_dedup: int = 0
    unique_samples: int = 0
    duplicates_removed: int = 0
    samples_skipped_min_questions: int = 0
    total_dual_zero_questions: int = 0
