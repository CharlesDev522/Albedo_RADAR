"""Schemas for Albedo scoring-results.jsonl dual-zero question analysis."""

from __future__ import annotations

from pydantic import BaseModel, Field


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
    export_filename: str | None = None
    total_samples: int = 0
    samples_with_dual_zeros: int = 0
    total_dual_zero_questions: int = 0
    samples: list[AlbedoSampleDualZeros] = Field(default_factory=list)
