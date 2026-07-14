"""Live in-progress duel snapshot from Albedo dashboard."""

from __future__ import annotations

from pydantic import BaseModel, Field


class AlbedoLiveDuelParticipant(BaseModel):
    uid: int | None = None
    hotkey: str | None = None
    repo: str | None = None
    model_name: str | None = None
    namespace: str | None = None
    model_uri: str | None = None
    king_version: int | None = None


class AlbedoLiveDuel(BaseModel):
    subnet: int = 97
    is_active: bool = False
    status: str = "idle"
    phase_label: str = "No duel in progress"
    eval_run_id: str | None = None
    submission_id: str | None = None
    pipeline_stage: str | None = None
    pipeline_detail: str | None = None
    challenger: AlbedoLiveDuelParticipant | None = None
    king: AlbedoLiveDuelParticipant | None = None
    progress_pct: float | None = None
    sample_count: int | None = None
    generated_sample_count: int | None = None
    started_at: str | None = None
    elapsed_seconds: float | None = None
    eval_queue_depth: int = 0
    pipeline_counts: dict[str, dict[str, int]] = Field(default_factory=dict)
    dashboard_url: str
    updated_at: str | None = None
    note: str = ""
