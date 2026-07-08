"""Schemas for Albedo scoring-results.jsonl dual-zero question analysis."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AlbedoDualZeroQuestion(BaseModel):
    question_id: str
    category: str | None = None
    text: str
    glm_explanation: str | None = None
    qwen_explanation: str | None = None


class AlbedoSampleDualZeros(BaseModel):
    sample_id: str
    sample_label: str
    challenger_score: float | None = None
    king_score: float | None = None
    dual_zero_count: int = 0
    questions: list[AlbedoDualZeroQuestion] = Field(default_factory=list)


class AlbedoScoringAnalysis(BaseModel):
    eval_run_id: str
    scoring_results_url: str | None = None
    challenger_repo: str | None = None
    king_model_name: str | None = None
    finished_at: str | None = None
    glm_judge: str | None = None
    qwen_judge: str | None = None
    side: str = "challenger"
    total_samples: int = 0
    samples_with_dual_zeros: int = 0
    total_dual_zero_questions: int = 0
    samples: list[AlbedoSampleDualZeros] = Field(default_factory=list)
