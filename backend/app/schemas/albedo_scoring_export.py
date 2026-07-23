"""Schemas for simple per-duel scoring-results.jsonl export."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AlbedoScoringExportDuel(BaseModel):
    eval_run_id: str
    finished_at: str
    model_uri: str
    repo: str | None = None
    challenger_label: str
    king_label: str | None = None
    challenger_won: bool
    coronated: bool
    scoring_mode: str | None = None
    scored_sample_count: int | None = None
    sample_line_count: int | None = None
    export_filename: str


class AlbedoScoringExportOverview(BaseModel):
    generated_at: str
    duels_total: int
    duels_with_scoring: int
    duels: list[AlbedoScoringExportDuel] = Field(default_factory=list)
